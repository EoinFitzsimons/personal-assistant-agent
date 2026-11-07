"""Polls the jobs table and runs planning jobs. Run with: python -m app.worker"""

import logging
import time
from datetime import timedelta

from sqlalchemy import and_, or_, select, update

from app.db import SessionLocal, init_db
from app.models import Job, Plan, utcnow
from app.pipeline.runner import run_plan_job

log = logging.getLogger("worker")
MAX_ATTEMPTS = 3
# A running job not updated for this long is assumed to belong to a dead worker and is reclaimed.
STALE_AFTER = timedelta(minutes=15)


def _claimable():
    stale = and_(Job.status == "running", Job.updated_at < utcnow() - STALE_AFTER, Job.attempts < MAX_ATTEMPTS)
    return or_(Job.status == "queued", stale)


def claim_next() -> Job | None:
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(_claimable()).order_by(Job.id).limit(1))
        if job is None:
            return None
        claimed = db.execute(
            update(Job).where(Job.id == job.id, _claimable())
            .values(status="running", attempts=Job.attempts + 1, updated_at=utcnow())
        ).rowcount
        db.commit()
        return job if claimed else None


def run_once() -> bool:
    job = claim_next()
    if job is None:
        return False
    status, error = "done", ""
    try:
        if job.type == "plan":
            run_plan_job(int(job.payload["plan_id"]), raise_errors=True)
        else:
            status, error = "failed", f"Unknown job type {job.type}"
    except Exception as exc:  # noqa: BLE001
        log.exception("Job %s failed", job.id)
        status = "queued" if job.attempts < MAX_ATTEMPTS else "failed"
        error = str(exc)[:2000]
    with SessionLocal() as db:
        db.execute(update(Job).where(Job.id == job.id).values(status=status, error=error))
        if status == "queued" and job.type == "plan":
            db.execute(update(Plan).where(Plan.id == int(job.payload["plan_id"])).values(status="gathering"))
        db.commit()
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    log.info("Worker started")
    while True:
        if not run_once():
            time.sleep(1.0)


if __name__ == "__main__":
    main()
