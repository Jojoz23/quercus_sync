from fastapi.testclient import TestClient

from quercus_sync.web import app


def test_health_and_demo_courses():
    client = TestClient(app)
    assert client.get("/api/health").json()["status"] == "ok"
    home = client.get("/")
    assert home.status_code == 200
    assert "Quercus Sync" in home.text
    courses = client.get("/api/courses").json()["courses"]
    assert any(row["course_code"].startswith("CSC148") for row in courses)
    assert any(row["course_code"].startswith("CSC108") and row["access"] == "past" for row in courses)
    assert all(row["course_code"] != "HIS101H5 F" for row in courses)
    me = client.get("/api/me").json()
    assert me["demo"] is True
    assert "Stop" in home.text
    assert "Paste access token" not in home.text
    assert "QUERCUS_TOKEN" in home.text


def test_stop_unknown_job():
    client = TestClient(app)
    assert client.post("/api/sync/missing/stop").status_code == 404


def test_stop_running_job():
    client = TestClient(app)
    started = client.post("/api/sync", json={"course_ids": [148001]})
    job_id = started.json()["job_id"]
    stopped = client.post(f"/api/sync/{job_id}/stop")
    assert stopped.status_code == 200
    assert stopped.json()["ok"] is True
