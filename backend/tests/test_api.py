from fastapi.testclient import TestClient

from app.main import app


def _client():
    c = TestClient(app)
    c.__enter__()
    return c


client = _client()


def _auth(email="ana@example.com"):
    r = client.post("/auth/signup", json={"email": email, "password": "supersecret", "name": "Anastasiia"})
    if r.status_code == 409:
        r = client.post("/auth/login", json={"email": email, "password": "supersecret"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_requires_auth():
    assert client.get("/plans/latest").status_code == 401


def test_full_demo_flow():
    h = _auth()
    s = client.get("/settings", headers=h).json()
    s["vip_people"] = ["Sarah Chen"]
    s["weekly_goals"] = ["Ship onboarding flow"]
    assert client.put("/settings", json=s, headers=h).status_code == 200

    created = client.post("/plans", headers=h)
    assert created.status_code == 201
    plan = client.get(f"/plans/{created.json()['id']}", headers=h).json()
    assert plan["status"] == "ready", plan["error"]
    kinds = {i["kind"] for i in plan["items"]}
    assert {"meeting", "commitment", "follow_up", "workout", "meal"} <= kinds
    assert any(i["status"] == "inbox" for i in plan["items"])
    assert plan["summary"]["sources"] == ["demo"]

    workout = next(i for i in plan["items"] if i["kind"] == "workout")
    r = client.post(f"/plans/{plan['id']}/chat", json={"message": "move my workout to 7:15am"}, headers=h)
    assert r.status_code == 200
    moved = next(i for i in r.json()["plan"]["items"] if i["id"] == workout["id"])
    assert moved["start"].startswith(f"{plan['date']}T07:15") and moved["fixed"]

    # Moving onto a meeting is rejected
    standup = next(i for i in plan["items"] if i["title"] == "Team stand-up")
    r = client.patch(f"/plans/{plan['id']}/items/{workout['id']}", json={"start": standup["start"][11:16]}, headers=h)
    assert r.status_code == 409

    inbox = next(i for i in plan["items"] if i["status"] == "inbox")
    r = client.patch(f"/plans/{plan['id']}/items/{inbox['id']}", json={"status": "proposed"}, headers=h)
    assert next(i for i in r.json()["items"] if i["id"] == inbox["id"])["start"] is not None

    r = client.post(f"/plans/{plan['id']}/approve", headers=h)
    assert all(i["status"] != "proposed" for i in r.json()["items"])


def test_cannot_read_other_users_plan():
    h1, h2 = _auth("a1@example.com"), _auth("a2@example.com")
    pid = client.post("/plans", headers=h1).json()["id"]
    assert client.get(f"/plans/{pid}", headers=h2).status_code == 404


def test_connections_listed_and_unconfigured_authorize_fails():
    h = _auth()
    conns = client.get("/connections", headers=h).json()
    assert {c["provider"] for c in conns} == {"slack", "microsoft", "fitbit", "oura"}
    assert client.get("/connections/slack/authorize", headers=h).status_code == 400
