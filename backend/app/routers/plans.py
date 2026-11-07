from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import ChatMessage, Job, Plan, PlanItem, User
from app.pipeline import chat_edit
from app.pipeline.runner import EditError, apply_ops, move_item, replan, run_plan_job, tomorrow_for, user_tz
from app.schemas import ChatIn, ChatOut, ItemPatch, PlanOut, PlanSummaryOut, ReviewIn
from app.security import current_user

router = APIRouter(prefix="/plans", tags=["plans"])


def _plan(db: Session, user: User, plan_id: int) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None or plan.user_id != user.id:
        raise HTTPException(404, "Plan not found")
    return plan


def progress_of(plan: Plan) -> list[str]:
    """What the user has done to a plan that a re-plan would discard."""
    marked = sum(bool(i.outcome) for i in plan.items)
    kept = sum(i.kind != "meeting" and (i.status == "approved" or i.fixed) for i in plan.items)
    removed = sum(i.status == "removed" for i in plan.items)
    parts = []
    if marked:
        parts.append(f"{marked} marked done or skipped")
    if kept:
        parts.append(f"{kept} kept or moved")
    if removed:
        parts.append(f"{removed} removed")
    if plan.review_note:
        parts.append("your review note")
    if plan.messages:
        parts.append("chat edits")
    return parts


@router.post("", response_model=PlanOut, status_code=201)
def create_plan(background: BackgroundTasks, replace: bool = False, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    day = tomorrow_for(user)
    existing = db.scalar(select(Plan).where(Plan.user_id == user.id, Plan.date == day, Plan.status == "ready")
                         .order_by(Plan.id.desc()).limit(1))
    progress = progress_of(existing) if existing else []
    if progress and not replace:
        raise HTTPException(409, f"Tomorrow already has progress ({', '.join(progress)}). Confirm to replace it.")
    plan = Plan(user_id=user.id, date=day, status="gathering")
    db.add(plan)
    db.commit()
    if get_settings().run_jobs_inline:
        background.add_task(run_plan_job, plan.id)
    else:
        db.add(Job(type="plan", payload={"plan_id": plan.id}))
        db.commit()
    db.refresh(plan)
    return plan


@router.get("/latest", response_model=PlanOut | None)
def latest_plan(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalar(select(Plan).where(Plan.user_id == user.id).order_by(Plan.id.desc()).limit(1))


@router.get("", response_model=list[PlanSummaryOut])
def list_plans(user: User = Depends(current_user), db: Session = Depends(get_db)):
    latest_per_day = select(func.max(Plan.id)).where(Plan.user_id == user.id).group_by(Plan.date)
    plans = db.scalars(select(Plan).where(Plan.id.in_(latest_per_day)).order_by(Plan.date.desc()).limit(30))
    out = []
    for p in plans:
        timed = [i for i in p.items if i.start and i.kind != "meeting" and i.status not in ("removed", "inbox", "unscheduled")]
        out.append(PlanSummaryOut(id=p.id, date=p.date, status=p.status, planned=len(timed),
                                  done=sum(i.outcome == "done" for i in timed),
                                  skipped=sum(i.outcome == "skipped" for i in timed)))
    return out


@router.get("/today", response_model=PlanOut | None)
def today_plan(user: User = Depends(current_user), db: Session = Depends(get_db)):
    today = tomorrow_for(user) - timedelta(days=1)
    return db.scalar(select(Plan).where(Plan.user_id == user.id, Plan.date == today, Plan.status == "ready")
                     .order_by(Plan.id.desc()).limit(1))


@router.post("/{plan_id}/review", response_model=PlanOut)
def save_review(plan_id: int, body: ReviewIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = _plan(db, user, plan_id)
    plan.review_note = body.note.strip()
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _plan(db, user, plan_id)


@router.patch("/{plan_id}/items/{item_id}", response_model=PlanOut)
def patch_item(plan_id: int, item_id: int, body: ItemPatch, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    plan = _plan(db, user, plan_id)
    item = db.get(PlanItem, item_id)
    if item is None or item.plan_id != plan.id:
        raise HTTPException(404, "Item not found")
    if body.outcome is not None:
        item.outcome = body.outcome
    if body.duration_min is None and body.start is None and body.status is None:
        db.commit()
        db.refresh(plan)
        return plan
    try:
        if body.duration_min is not None:
            ops_errors = apply_ops(db, plan, [{"op": "resize", "item_id": item.id, "duration_min": body.duration_min}])
            if ops_errors:
                raise EditError(ops_errors[0])
        if body.start is not None:
            move_item(plan, item, body.start)
        if body.status is not None:
            if item.kind == "meeting" and body.status == "removed":
                raise EditError("Meetings can't be removed in v1 (read-only calendar).")
            item.status = body.status
    except EditError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    db.flush()
    replan(db, plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/{plan_id}/approve", response_model=PlanOut)
def approve_all(plan_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = _plan(db, user, plan_id)
    for item in plan.items:
        if item.status == "proposed":
            item.status = "approved"
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/{plan_id}/chat", response_model=ChatOut)
def chat(plan_id: int, body: ChatIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = _plan(db, user, plan_id)
    if plan.status != "ready":
        raise HTTPException(409, "The plan is still being prepared")
    tz = user_tz(user)
    items = [
        {"id": i.id, "kind": i.kind, "tag": i.tag, "title": i.title, "status": i.status,
         "start": i.start.astimezone(tz).strftime("%H:%M") if i.start else None, "duration_min": i.duration_min}
        for i in plan.items if i.status not in ("removed",)
    ]
    ops, reply = chat_edit.parse(body.message, items)
    errors = apply_ops(db, plan, ops) if ops else []
    if errors:
        reply = (reply + " " if ops and len(errors) < len(ops) else "") + " ".join(errors)
    db.add(ChatMessage(plan_id=plan.id, role="user", content=body.message))
    db.add(ChatMessage(plan_id=plan.id, role="assistant", content=reply, ops=ops))
    db.commit()
    db.refresh(plan)
    return ChatOut(reply=reply, plan=PlanOut.model_validate(plan))
