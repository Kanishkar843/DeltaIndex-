import json
from pathlib import Path
import httpx, pytest
from sqlalchemy import text
from app.store import Index
from app.adapters import greenhouse, AdapterError, local_file


@pytest.fixture
def idx(tmp_path):
    i = Index("sqlite:///" + str(tmp_path / "extended.db"))
    i.migrate()
    return i


@pytest.fixture
def rows():
    return json.loads(Path("data/jobs.json").read_text())[:3]


def test_cross_source_dedup_and_versions(idx, rows):
    assert idx.ingest("a", rows)["embeddings"] == 3
    assert idx.ingest("b", rows)["embeddings"] == 0
    assert len(idx.jobs()) == 6
    assert idx.search("engineer")["total"] == 3
    with idx.engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM embedding_versions")).scalar() == 3
        assert c.execute(text("SELECT count(*) FROM job_postings")).scalar() == 6
        assert c.execute(text("SELECT count(*) FROM retrieval_events")).scalar() == 1
    assert idx.deactivate_stale("2999-01-01T00:00:00+00:00") == 6
    assert idx.search("engineer")["total"] == 0


def test_greenhouse_retry_and_sanitization():
    attempts = []

    def handler(req):
        attempts.append(req)
        if len(attempts) < 2:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 1,
                        "title": "Engineer",
                        "content": "<p>Build &amp; test</p>",
                        "location": {"name": "Remote"},
                        "absolute_url": "https://example.org/job",
                    }
                ]
            },
        )

    rows = greenhouse("demo", httpx.MockTransport(handler), lambda _: None)
    assert (
        len(attempts) == 2
        and rows[0]["description"] == "Build & test"
        and not rows[0]["synthetic"]
    )
    with pytest.raises(ValueError):
        greenhouse("../bad")
    with pytest.raises(AdapterError):
        greenhouse(
            "demo", httpx.MockTransport(lambda r: httpx.Response(503)), lambda _: None
        )


def test_jsonl_validation(tmp_path, rows):
    file = tmp_path / "jobs.jsonl"
    file.write_text("\n".join(json.dumps(r) for r in rows))
    assert len(local_file(file)) == 3
    file.write_text("not json")
    with pytest.raises(ValueError):
        local_file(file)


def test_source_outage_preserves_then_recovers(idx, rows, monkeypatch):
    idx.ingest("board", rows, True)
    with idx.engine.begin() as c:
        c.execute(
            text(
                "UPDATE sources SET adapter='greenhouse',config=:config WHERE id='board'"
            ),
            {"config": json.dumps({"board": "demo"})},
        )

    def fail(*args):
        raise AdapterError("Unavailable")

    monkeypatch.setattr("app.adapters.greenhouse", fail)
    with pytest.raises(AdapterError):
        idx.run_source("board")
    assert len(idx.jobs()) == 3
    with idx.engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM ingestion_failures")).scalar() == 1
    monkeypatch.setattr("app.adapters.greenhouse", lambda *_: rows[:2])
    assert idx.run_source("board")["deactivated"] == 1
    assert len(idx.jobs()) == 2


def test_metadata_only_change_and_personalization(idx, rows):
    from app.core import preferences

    idx.ingest("source", rows)
    rows[0]["salary_min"] = 10000
    assert idx.ingest("source", rows)["embeddings"] == 0
    base = idx.search("engineer")
    idx.embedder.version = "fixture-hash-v2"
    assert idx.search("engineer")["cache"] == "miss"
    job = base["results"][0]["job"]
    features = preferences(
        job, job["skills"], job["remote"], job["location"], job["seniority"]
    )
    assert (
        features["skills"] == 0.02
        and features["location"] == 0.01
        and features["seniority"] == 0.01
    )


def test_greenhouse_long_description_keeps_batch_and_provenance():
    source_url = "https://example.org/original-job"
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 123,
                        "title": "Engineer",
                        "content": "x" * 20000,
                        "location": {"name": "Remote"},
                        "absolute_url": source_url,
                    }
                ]
            },
        )
    )
    rows = greenhouse("demo", transport, lambda _: None)
    assert len(rows) == 1
    assert len(rows[0]["description"]) == 10000
    assert rows[0]["description"].endswith(
        "[Description shortened; see original job URL.]"
    )
    assert rows[0]["url"] == source_url and not rows[0]["synthetic"]
