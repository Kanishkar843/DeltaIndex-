"""Explicit PostgreSQL/pgvector + Redis tests; no fallback services."""

import json, os, subprocess, sys
from pathlib import Path
from uuid import uuid4
from sqlalchemy import text
from app.store import Index


def test_real_postgres_vector_redis():
    url = os.environ.get("TEST_DATABASE_URL", "")
    redis_url = os.environ.get("TEST_REDIS_URL", "")
    assert url.startswith("postgresql") and redis_url.startswith("redis://")
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": url},
        check=True,
        capture_output=True,
    )
    idx = Index(url, "fixture", redis_url)
    assert idx.cache.ping()
    source = "acceptance-" + uuid4().hex
    rows = json.loads(Path("data/jobs.json").read_text())[:12]
    with idx.engine.connect() as c:
        assert c.execute(
            text("SELECT extversion FROM pg_extension WHERE extname='vector'")
        ).scalar()
        assert (
            c.execute(text("SELECT version_num FROM alembic_version")).scalar()
            == "0002"
        )
    first = idx.ingest(source, rows, True)
    assert first["created"] == 12
    assert idx.ingest(source, rows, True)["embeddings"] == 0
    q = "python backend " + uuid4().hex
    assert idx.search(q)["cache"] == "miss"
    assert idx.search(q)["cache"] == "hit"
    rows[0]["description"] += " acceptance changed " + uuid4().hex
    changed = idx.ingest(source, rows, True)
    assert changed["updated"] == 1 and changed["embeddings"] == 1
    assert idx.search(q)["cache"] == "miss"
    metadata = [dict(r) for r in rows]
    metadata[0]["salary_min"] = 12345
    assert idx.ingest(source, metadata, True)["embeddings"] == 0
    assert idx.ingest(source, metadata[:-1], True)["deactivated"] == 1
    before = idx.search("python", limit=100)["total"]
    assert idx.ingest(source + "-mirror", metadata[:-1], True)["embeddings"] == 0
    assert idx.search("python", limit=100)["total"] == before
    for mode in ("keyword", "semantic", "hybrid"):
        result = idx.search("python", mode, limit=100)
        assert result["results"] and result["lexical_engine"] == "PostgreSQL ts_rank_cd"
    assert idx.search("python", location="'; DROP TABLE jobs; --")["total"] == 0
    # Only this test's postings are marked old; do not expire unrelated data.
    with idx.engine.begin() as c:
        c.execute(
            text(
                "UPDATE job_postings SET last_seen='1900-01-01' WHERE source_id IN (:a,:b)"
            ),
            {"a": source, "b": source + "-mirror"},
        )
    assert idx.deactivate_stale("1901-01-01") == 22
    idx.engine.dispose()
