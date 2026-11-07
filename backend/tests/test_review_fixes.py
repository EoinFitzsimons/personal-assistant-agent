from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from app import worker
from app.config import Settings
from app.db import SessionLocal
from app.models import Job, Plan, utcnow
from app.pipeline import commitments
from app.security import create_token
from tests.helpers import demo_data
from tests.test_api import _auth, client


def _plan_for(h, tz="UTC"):
    s = client.get("/settings", headers=h).json()
    s["timezone"] = tz
    client.put("/settings", json=s, headers=h)
    pid = client.post("/plans", headers=h).json()["id"]
    return client.get(f"/plans/{pid}", headers=h).json()


def _meeting_starts(plan):
    return {i["id"]: datetime.fromisoformat(i["start"].replace("Z", "+00:00")) for i in plan["items"] if i["kind"] == "meeting"}


def test_edits_keep_meeting_times_outside_utc():
    h = _auth("ny@example.com")
    plan = _plan_for(h, "America/New_York")
    before = _meeting_starts(plan)
    r = client.post(f"/plans/{plan['id']}/chat", json={"message": "move my workout to 7am"}, headers=h)
    assert r.status_code == 200
    after = r.json()["plan"]
    assert _meeting_starts(after) == before
    standup = next(i for i in after["items"] if i["title"] == "Team stand-up")
    assert standup["start"][11:16] == "09:30"  # wall-clock time in the user's timezone
    workout = next(i for i in after["items"] if i["kind"] == "workout")
    assert workout["start"][11:16] == "07:00"


def test_rejected_patch_does_not_persist_resize():
    h = _auth("patch@example.com")
    plan = _plan_for(h)
    workout = next(i for i in plan["items"] if i["kind"] == "workout")
    standup = next(i for i in plan["items"] if i["title"] == "Team stand-up")
    r = client.patch(f"/plans/{plan['id']}/items/{workout['id']}",
                     json={"duration_min": 90, "start": standup["start"][11:16]}, headers=h)
    assert r.status_code == 409
    after = client.get(f"/plans/{plan['id']}", headers=h).json()
    assert next(i for i in after["items"] if i["id"] == workout["id"])["duration_min"] == workout["duration_min"]


def test_oauth_completion_bound_to_signed_in_user():
    h = _auth("oauth@example.com")
    r = client.get("/connections/slack/callback", params={"code": "c1", "state": "s1"}, follow_redirects=False)
    assert r.status_code in (302, 307) and "code=c1" in r.headers["location"] and "/settings?" in r.headers["location"]
    attacker_state = create_token(999, purpose="oauth", ttl=timedelta(minutes=5), extra={"provider": "slack"})
    r = client.post("/connections/slack/complete", json={"code": "c1", "state": attacker_state}, headers=h)
    assert r.status_code == 400


def test_default_jwt_secret_rejected_outside_development():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", jwt_secret="dev-secret-change-me")
    Settings(_env_file=None, app_env="production", jwt_secret="x" * 32)


def test_llm_non_numeric_confidence_does_not_abort(monkeypatch):
    monkeypatch.setattr(commitments.llm, "is_enabled", lambda: True)
    monkeypatch.setattr(commitments.llm, "complete_json", lambda *a, **k: {
        "results": [{"index": 0, "is_commitment": True, "task": "Do it", "confidence": "high"}]})
    cands = commitments.detect(demo_data().items, "Anastasiia")
    assert any(c.kind == "commitment" and c.confidence == 0.7 for c in cands)


def _job(db, **kw):
    plan = Plan(user_id=1, date=utcnow().date(), status="gathering")
    db.add(plan)
    db.flush()
    job = Job(type="plan", payload={"plan_id": plan.id}, **kw)
    db.add(job)
    db.commit()
    return job.id, plan.id


def test_worker_reclaims_stale_job_and_retries_failures(monkeypatch):
    _auth("worker@example.com")
    with SessionLocal() as db:
        db.query(Job).delete()
        job_id, plan_id = _job(db, status="running", attempts=1, updated_at=utcnow() - timedelta(hours=1))

    def boom(*_a, **_k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(worker, "run_plan_job", boom)
    assert worker.run_once()
    with SessionLocal() as db:
        job, plan = db.get(Job, job_id), db.get(Plan, plan_id)
        assert (job.status, job.attempts) == ("queued", 2)
        assert plan.status == "gathering"
        db.query(Job).delete()
        db.commit()
