import os

os.environ["DATABASE_URL"] = "sqlite:///./test-api.db"
os.environ["ADMIN_TOKEN"] = "test-token"
from fastapi.testclient import TestClient
from app.main import app


def test_auth_ingest_search():
    with TestClient(app) as c:
        assert c.post("/ingest/seed").status_code == 401
        h = {"Authorization": "Bearer test-token"}
        assert c.post("/ingest/seed", headers=h).status_code == 200
        assert c.post("/ingest/seed", headers=h).json()["embeddings"] == 0
        result = c.get("/search", params={"q": "python", "remote": True}).json()
        assert result["results"] and all(r["job"]["remote"] for r in result["results"])
        assert c.get("/search", params={"q": "x", "mode": "invalid"}).status_code == 422
        assert c.get("/jobs", params={"limit": -1}).status_code == 422
        assert (
            c.post("/saved-searches", headers=h, json={"query": "python"}).status_code
            == 200
        )
        assert c.get("/saved-searches", headers=h).json()
        assert c.get("/").status_code == 200
