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
