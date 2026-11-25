import os, json, secrets
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import text
from .store import Index
from .core import Posting
from datetime import datetime, timezone
from .adapters import AdapterError

index = Index()


@asynccontextmanager
async def lifespan(app):
    if not index.pg:
        index.migrate()
    yield


app = FastAPI(title="DeltaIndex", lifespan=lifespan)


def admin(authorization: str = Header(default="")):
    expected = os.getenv("ADMIN_TOKEN")
    if not expected:
        raise HTTPException(503, "Set ADMIN_TOKEN to enable mutations")
    if not secrets.compare_digest(authorization, "Bearer " + expected):
        raise HTTPException(401, "Invalid admin token")


class Batch(BaseModel):
    source: str = Field(default="synthetic", pattern=r"^[a-zA-Z0-9_-]{1,128}$")
    postings: list[Posting] = Field(max_length=2000)
    full_snapshot: bool = False


@app.get("/health")
def health():
    return {
        "status": "ok",
        "embedding_mode": index.embedder.version,
        "database": index.engine.dialect.name,
        "cache": "redis" if index.cache else "native-test-memory",
    }


@app.post("/ingest/run", dependencies=[Depends(admin)])
def ingest(data: Batch):
    try:
        return index.ingest(
            data.source, [p.model_dump() for p in data.postings], data.full_snapshot
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/ingest/seed", dependencies=[Depends(admin)])
def seed():
    return index.ingest(
        "synthetic",
        json.loads((Path(__file__).parent.parent / "data/jobs.json").read_text()),
        True,
    )


@app.get("/ingest/status")
def status():
    with index.engine.connect() as c:
        return [
            dict(r) | {"stats": json.loads(r["stats"])}
            for r in c.execute(
                text("SELECT * FROM source_runs ORDER BY created_at DESC LIMIT 20")
            ).mappings()
        ]


@app.get("/jobs")
def jobs(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return index.jobs()[offset : offset + limit]


@app.get("/search")
@app.get("/search/explain")
def search(
    q: str = Query(min_length=1, max_length=500),
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid",
    location: str = "",
    remote: bool = False,
    skills: str = "",
    k: int = Query(60, ge=1, le=200),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    seniority: str = "",
    profile_id: str | None = None,
):
    weights = None
    if profile_id:
        with index.engine.connect() as c:
            stored = c.execute(
                text("SELECT preferences FROM profiles WHERE id=:id"),
                {"id": profile_id},
            ).scalar()
        if not stored:
            raise HTTPException(404, "Profile not found")
        pref = json.loads(stored)
        skills = skills or ",".join(pref["skills"])
        location = location or pref["location"]
        seniority = seniority or pref["seniority"]
        remote = remote or pref["remote"]
        weights = pref["weights"]
    return index.search(
        q,
        mode,
        location,
        remote,
        tuple(x.strip().lower() for x in skills.split(",") if x.strip()),
        k,
        limit,
        offset,
        seniority,
        weights,
    )


class Saved(BaseModel):
    query: str = Field(min_length=1, max_length=500)


@app.post("/saved-searches", dependencies=[Depends(admin)])
def save(data: Saved):
    identity = str(uuid4())
    with index.engine.begin() as c:
        c.execute(
            text("INSERT INTO saved_searches VALUES (:id,:q)"),
            {"id": identity, "q": data.query},
        )
    return {"id": identity}


@app.get("/saved-searches", dependencies=[Depends(admin)])
def saved():
    with index.engine.connect() as c:
        return [
            dict(r) for r in c.execute(text("SELECT * FROM saved_searches")).mappings()
        ]


class Feedback(BaseModel):
    job_id: str
    useful: bool


@app.post("/feedback", dependencies=[Depends(admin)])
def feedback(data: Feedback):
    with index.engine.begin() as c:
        c.execute(
            text("INSERT INTO feedback_events VALUES (:id,:job,:useful)"),
            {"id": str(uuid4()), "job": data.job_id, "useful": int(data.useful)},
        )
    return {"saved": True}


class Preferences(BaseModel):
    skills: list[str] = Field(default_factory=list, max_length=30)
    remote: bool = False
    location: str = Field(default="", max_length=200)
    seniority: str = Field(default="", max_length=40)
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "skills": 0.02,
            "remote": 0.01,
            "location": 0.01,
            "freshness": 0.005,
            "seniority": 0.01,
        }
    )


@app.get("/profiles", dependencies=[Depends(admin)])
def profiles():
    with index.engine.connect() as c:
        return [
            {"id": r["id"], **json.loads(r["preferences"])}
            for r in c.execute(text("SELECT * FROM profiles")).mappings()
        ]


@app.post("/profiles", dependencies=[Depends(admin)])
def save_profile(data: Preferences):
    if any(
        k not in {"skills", "remote", "location", "freshness", "seniority"}
        or not 0 <= v <= 1
        for k, v in data.weights.items()
    ):
        raise HTTPException(422, "Invalid ranking weights")
    identity = str(uuid4())
    with index.engine.begin() as c:
        c.execute(
            text("INSERT INTO profiles VALUES (:id,:p,:stamp)"),
            {
                "id": identity,
                "p": data.model_dump_json(),
                "stamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    return {"id": identity}


class Source(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    board: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    interval_seconds: int = Field(default=3600, ge=300, le=604800)


@app.post("/sources", dependencies=[Depends(admin)])
def source(data: Source):
    with index.engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO sources VALUES (:id,'greenhouse',:config,:interval,NULL,NULL) ON CONFLICT(id) DO UPDATE SET config=:config,interval_seconds=:interval,adapter='greenhouse'"
            ),
            {
                "id": data.id,
                "config": json.dumps({"board": data.board}),
                "interval": data.interval_seconds,
            },
        )
    return {"id": data.id}


@app.get("/sources", dependencies=[Depends(admin)])
def sources():
    with index.engine.connect() as c:
        return [dict(r) for r in c.execute(text("SELECT * FROM sources")).mappings()]


@app.post("/sources/{source_id}/run", dependencies=[Depends(admin)])
def run_source(source_id: str):
    try:
        return index.run_source(source_id)
    except ValueError as error:
        raise HTTPException(422, str(error))
    except AdapterError:
        raise HTTPException(
            502, "Source unavailable after bounded retries; existing index preserved"
        )


@app.get("/ingest/freshness")
def freshness():
    with index.engine.connect() as c:
        return [
            dict(r)
            for r in c.execute(
                text(
                    "SELECT substr(last_seen,1,10) AS day,COUNT(*) AS postings FROM job_postings WHERE status='active' GROUP BY substr(last_seen,1,10) ORDER BY day"
                )
            ).mappings()
        ]


@app.get("/ingest/failures", dependencies=[Depends(admin)])
def failures():
    with index.engine.connect() as c:
        return [
            dict(r)
            for r in c.execute(
                text(
                    "SELECT * FROM ingestion_failures ORDER BY created_at DESC LIMIT 100"
                )
            ).mappings()
        ]


@app.get("/ready")
def ready():
    with index.engine.connect() as c:
        c.execute(text("SELECT 1"))
    if index.cache:
        index.cache.ping()
    return {"ready": True}


static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static), name="static")
FRONTEND = Path(__file__).parent.parent / "frontend/dist"
if (FRONTEND / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(
        FRONTEND / "index.html"
        if (FRONTEND / "index.html").exists()
        else static / "index.html"
    )


@app.get("/legacy", include_in_schema=False)
def legacy():
    return FileResponse(static / "index.html")
