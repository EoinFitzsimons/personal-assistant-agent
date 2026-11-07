"""Polls the jobs table and runs planning jobs. Run with: python -m app.worker"""

import logging
import time

from sqlalchemy import select, update

from app.db import SessionLocal, init_db
from app.models import Job
from app.pipeline.runner import run_plan_job

log = logging.getLogger("worker")
MAX_ATTEMPTS = 3


def claim_next() -> Job | None:
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.status == "queued").order_by(Job.id).limit(1))
        if job is None:
            return None
        claimed = db.execute(
            update(Job).where(Job.id == job.id, Job.status == "queued")
            .values(status="running", attempts=Job.attempts + 1)
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
            run_plan_job(int(job.payload["plan_id"]))
        else:
            status, error = "failed", f"Unknown job type {job.type}"
    except Exception as exc:  # noqa: BLE001
        log.exception("Job %s failed", job.id)
        status = "queued" if job.attempts + 1 < MAX_ATTEMPTS else "failed"
        error = str(exc)[:2000]
    with SessionLocal() as db:
        db.execute(update(Job).where(Job.id == job.id).values(status=status, error=error))
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
