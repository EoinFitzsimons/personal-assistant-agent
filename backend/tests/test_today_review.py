from tests.test_api import _auth, client


def test_outcomes_review_and_history():
    h = _auth("loop@example.com")
    pid = client.post("/plans", headers=h).json()["id"]
    plan = client.get(f"/plans/{pid}", headers=h).json()
    workout = next(i for i in plan["items"] if i["kind"] == "workout")
    r = client.patch(f"/plans/{pid}/items/{workout['id']}", json={"outcome": "done"}, headers=h)
    assert r.status_code == 200
    assert next(i for i in r.json()["items"] if i["id"] == workout["id"])["outcome"] == "done"
    assert client.patch(f"/plans/{pid}/items/{workout['id']}", json={"outcome": "nope"}, headers=h).status_code == 422
    r = client.post(f"/plans/{pid}/review", json={"note": "Good focus morning"}, headers=h)
    assert r.json()["review_note"] == "Good focus morning"
    hist = client.get("/plans", headers=h).json()
    assert hist[0]["id"] == pid and hist[0]["done"] == 1 and hist[0]["planned"] >= 1
    assert client.get("/plans/today", headers=h).json() is None
    other = _auth("loop2@example.com")
    assert client.post(f"/plans/{pid}/review", json={"note": "x"}, headers=other).status_code == 404


def test_outcome_only_patch_keeps_schedule():
    h = _auth("noreplan@example.com")
    pid = client.post("/plans", headers=h).json()["id"]
    plan = client.get(f"/plans/{pid}", headers=h).json()
    s = client.get("/settings", headers=h).json()
    s["working_hours"] = {"start": "13:00", "end": "17:00"}
    client.put("/settings", json=s, headers=h)
    item = next(i for i in plan["items"] if i["kind"] == "workout")
    after = client.patch(f"/plans/{pid}/items/{item['id']}", json={"outcome": "done"}, headers=h).json()
    assert {i["id"]: i["start"] for i in after["items"]} == {i["id"]: i["start"] for i in plan["items"]}


def test_history_lists_older_days_after_many_replans():
    from datetime import date, timedelta

    from app.db import SessionLocal
    from app.models import Plan, User

    h = _auth("history@example.com")
    with SessionLocal() as db:
        uid = db.query(User).filter_by(email="history@example.com").one().id
        old = date(2026, 1, 1)
        db.add(Plan(user_id=uid, date=old, status="ready"))
        db.add_all(Plan(user_id=uid, date=old + timedelta(days=1), status="ready") for _ in range(31))
        db.commit()
    dates = [p["date"] for p in client.get("/plans", headers=h).json()]
    assert dates == ["2026-01-02", "2026-01-01"]


def test_llm_reasons_keep_goal_link(monkeypatch):
    from app.pipeline import rank as rank_mod
    from app.pipeline.commitments import detect
    from tests.helpers import demo_data

    cands = detect(demo_data().items, "Anastasiia")
    monkeypatch.setattr(rank_mod.llm, "is_enabled", lambda: True)
    monkeypatch.setattr(rank_mod.llm, "complete_json", lambda *a, **k: {
        "results": [{"index": i, "priority": 50, "duration_min": 30, "reason": "Important."} for i in range(len(cands))]})
    ranked = rank_mod.rank(cands, {"weekly_goals": ["Ship onboarding flow"]})
    linked = [r for r in ranked if 'goal "Ship onboarding flow"' in r.reason]
    assert linked and all(r.reason.startswith("Important.") for r in linked)
