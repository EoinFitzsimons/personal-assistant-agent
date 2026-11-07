import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import get_settings
from app.connectors.base import ConnectorError
from app.connectors.registry import DEMO, get_connector
from app.connectors.types import FetchContext, SyncResult
from app.db import SessionLocal
from app.models import Connection, Plan, PlanItem, User
from app.pipeline import commitments as commitments_mod
from app.pipeline.rank import rank
from app.pipeline.scheduler import Block, meal_blocks, overlaps, parse_hhmm, schedule, workout_block
from app.security import decrypt, encrypt

log = logging.getLogger(__name__)


def user_tz(user: User) -> ZoneInfo:
    return ZoneInfo(user.settings.get("timezone") or "UTC")


def tomorrow_for(user: User) -> date:
    return datetime.now(user_tz(user)).date() + timedelta(days=1)


def _context(user: User, day: date) -> FetchContext:
    tz = user_tz(user)
    day_start = datetime.combine(day, time(0, 0), tzinfo=tz)
    now = datetime.now(timezone.utc)
    return FetchContext(
        since=now - timedelta(hours=get_settings().lookback_hours),
        day_start=day_start, day_end=day_start + timedelta(days=1),
        today=datetime.now(tz).date(), user_name=user.name or user.email.split("@")[0],
    )


def _access_token(db: Session, conn: Connection) -> str:
    connector = get_connector(conn.provider)
    if conn.expires_at and conn.refresh_token_enc and connector:
        expires = conn.expires_at if conn.expires_at.tzinfo else conn.expires_at.replace(tzinfo=timezone.utc)
        if expires - timedelta(minutes=2) < datetime.now(timezone.utc):
            tokens = connector.refresh(decrypt(conn.refresh_token_enc))
            conn.access_token_enc = encrypt(tokens.access_token)
            if tokens.refresh_token:
                conn.refresh_token_enc = encrypt(tokens.refresh_token)
            conn.expires_at = (datetime.now(timezone.utc) + timedelta(seconds=tokens.expires_in)
                               if tokens.expires_in else None)
            db.commit()
    return decrypt(conn.access_token_enc)


def gather(db: Session, user: User, day: date) -> tuple[SyncResult, list[str]]:
    ctx = _context(user, day)
    result = SyncResult()
    sources: list[str] = []
    if user.settings.get("demo_mode") or not user.connections:
        result.extend(DEMO.fetch("demo", ctx))
        return result, ["demo"]
    for conn in user.connections:
        connector = get_connector(conn.provider)
        if connector is None:
            continue
        if connector.category == "health" and not user.settings.get("health_consent"):
            continue
        try:
            result.extend(connector.fetch(_access_token(db, conn), ctx))
            sources.append(conn.provider)
        except (ConnectorError, Exception) as exc:  # noqa: BLE001 - one failing source must not kill the plan
            log.exception("Fetch failed for %s", conn.provider)
            result.errors.append(f"{connector.display_name}: {exc}")
    return result, sources


def _to_item(plan: Plan, b: Block) -> PlanItem:
    return PlanItem(
        plan_id=plan.id, kind=b.kind, title=b.title, details=b.details, start=b.start, end=b.end,
        duration_min=b.duration_min, priority=b.priority, reason=b.reason, source_provider=b.source_provider,
        source_link=b.source_link, owed_to=b.owed_to, confidence=b.confidence, status=b.status, fixed=b.fixed,
        tag=b.tag,
    )


def build_plan(db: Session, plan: Plan) -> None:
    user = plan.user
    settings = user.settings
    tz = user_tz(user)
    plan.status = "gathering"
    db.commit()
    data, sources = gather(db, user, plan.date)

    plan.status = "planning"
    db.commit()
    candidates = commitments_mod.detect(data.items, user.name)
    ranked = rank(candidates, settings)

    fixed = [Block(kind="meeting", title=e.title, duration_min=int((e.end - e.start).total_seconds() // 60),
                   start=e.start.astimezone(tz), end=e.end.astimezone(tz), fixed=True, source_provider=e.provider,
                   source_link=e.link, details=", ".join(e.attendees[:6]), status="approved")
             for e in data.events if not e.all_day or e.show_as in ("busy", "oof")]
    flexible: list[Block] = meal_blocks(plan.date, settings)
    flexible.append(workout_block(plan.date, settings, data.health))
    inbox: list[Block] = []
    for r in ranked:
        c = r.candidate
        block = Block(kind=c.kind, title=c.title, duration_min=r.duration_min, priority=r.priority, reason=r.reason,
                      details=c.details, source_provider=c.source_provider, source_link=c.source_link,
                      owed_to=c.owed_to, confidence=c.confidence)
        if c.kind == "commitment" and c.confidence < commitments_mod.INBOX_THRESHOLD:
            block.status = "inbox"
            inbox.append(block)
        else:
            flexible.append(block)

    placed = schedule(plan.date, settings, fixed, flexible)
    for item in list(plan.items):
        db.delete(item)
    db.flush()
    for b in placed + inbox:
        db.add(_to_item(plan, b))

    metrics = {m.name: m.value for m in sorted(data.health, key=lambda m: m.day)}
    plan.summary = {
        "sources": sources,
        "counts": {"messages": sum(i.kind == "message" for i in data.items),
                   "emails": sum(i.kind == "email" for i in data.items), "meetings": len(fixed),
                   "commitments": sum(c.kind == "commitment" for c in candidates),
                   "follow_ups": sum(c.kind == "follow_up" for c in candidates)},
        "health": metrics,
        "errors": data.errors,
    }
    plan.status = "ready"
    db.commit()


def run_plan_job(plan_id: int, raise_errors: bool = False) -> None:
    db = SessionLocal()
    try:
        plan = db.get(Plan, plan_id)
        if plan is None:
            return
        try:
            build_plan(db, plan)
        except Exception as exc:  # noqa: BLE001
            log.exception("Plan %s failed", plan_id)
            db.rollback()
            plan.status, plan.error = "failed", str(exc)[:2000]
            db.commit()
            if raise_errors:
                raise
    finally:
        db.close()


def _block_of(item: PlanItem) -> Block:
    return Block(kind=item.kind, title=item.title, duration_min=item.duration_min, start=item.start, end=item.end,
                 fixed=item.fixed or item.kind == "meeting", priority=item.priority, status=item.status, tag=item.tag,
                 ref=item.id)


def _aware(dt: datetime | None, tz: ZoneInfo) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(tz) if dt.tzinfo is None else dt.astimezone(tz)


def replan(db: Session, plan: Plan) -> None:
    """Re-place every non-fixed item after an edit, keeping pinned items and meetings in place."""
    tz = user_tz(plan.user)
    fixed, flexible = [], []
    for item in plan.items:
        if item.status in ("removed", "inbox"):
            continue
        b = _block_of(item)
        b.start, b.end = _aware(b.start, tz), _aware(b.end, tz)
        (fixed if b.fixed else flexible).append(b)
    by_id = {i.id: i for i in plan.items}
    for b in schedule(plan.date, plan.user.settings, fixed, flexible):
        item = by_id[b.ref]
        item.start, item.end, item.status = b.start, b.end, b.status
    db.flush()


class EditError(ValueError):
    pass


def _check_free(plan: Plan, start: datetime, end: datetime, ignore_id: int | None) -> None:
    tz = user_tz(plan.user)
    blockers = []
    for i in plan.items:
        if i.id == ignore_id or i.status in ("removed", "inbox", "unscheduled") or not (i.fixed or i.kind == "meeting"):
            continue
        b = _block_of(i)
        b.start, b.end = _aware(b.start, tz), _aware(b.end, tz)
        blockers.append(b)
    clash = overlaps(start, end, blockers)
    if clash:
        raise EditError(f"That overlaps with \"{clash.title}\" ({clash.start:%H:%M}–{clash.end:%H:%M}).")


def move_item(plan: Plan, item: PlanItem, hhmm: str) -> None:
    if item.kind == "meeting":
        raise EditError("Meetings come from your calendar and can't be moved in v1.")
    start = parse_hhmm(plan.date, hhmm, user_tz(plan.user))
    end = start + timedelta(minutes=item.duration_min)
    _check_free(plan, start, end, item.id)
    item.start, item.end, item.fixed = start, end, True
    if item.status in ("unscheduled", "inbox", "removed"):
        item.status = "proposed"


def apply_ops(db: Session, plan: Plan, ops: list[dict]) -> list[str]:
    errors: list[str] = []
    items = {i.id: i for i in plan.items}
    for op in ops:
        try:
            kind = op.get("op")
            if kind == "add":
                start = parse_hhmm(plan.date, op["start"], user_tz(plan.user))
                dur = int(op.get("duration_min", 30))
                _check_free(plan, start, start + timedelta(minutes=dur), None)
                new = PlanItem(plan_id=plan.id, kind="task", title=op["title"], start=start,
                               end=start + timedelta(minutes=dur), duration_min=dur, fixed=True, priority=80,
                               reason="Added by you.", status="proposed")
                db.add(new)
                plan.items.append(new)
                continue
            item = items.get(int(op.get("item_id", -1)))
            if item is None:
                raise EditError("I couldn't find that item in your plan.")
            if kind == "move":
                move_item(plan, item, op["start"])
            elif kind == "remove":
                if item.kind == "meeting":
                    raise EditError("Meetings can't be removed in v1 (read-only calendar).")
                item.status = "removed"
            elif kind == "resize":
                dur = int(op["duration_min"])
                if item.fixed and item.start and item.kind != "meeting":
                    start = _aware(item.start, user_tz(plan.user))
                    _check_free(plan, start, start + timedelta(minutes=dur), item.id)
                    item.end = start + timedelta(minutes=dur)
                item.duration_min = dur
                if item.kind == "workout":
                    item.title = f"{item.title.split(' (')[0]} ({dur} min)"
            else:
                raise EditError(f"Unknown edit: {kind}")
        except (EditError, KeyError, ValueError) as exc:
            errors.append(str(exc))
    db.flush()
    replan(db, plan)
    return errors
