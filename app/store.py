import os, json, hashlib, time
from uuid import uuid4
from . import schema
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from .core import Posting, content, digest, Embedder, rrf, preferences, tokens


class Index:
    def __init__(self, url=None, mode=None, redis_url=None):
        self.engine = create_engine(
            url or os.getenv("DATABASE_URL", "sqlite:///./deltaindex.db")
        )
        self.pg = self.engine.dialect.name == "postgresql"
        self.embedder = Embedder(mode or os.getenv("EMBEDDING_MODE", "fixture"))
        self.cache = None
        self.local_cache = {}
        redis_url = redis_url or os.getenv("REDIS_URL")
        if redis_url:
            import redis

            self.cache = redis.Redis.from_url(
                redis_url, decode_responses=True, socket_timeout=2
            )

    def migrate(self):
        vector_type = "vector" if self.pg else "TEXT"
        with self.engine.begin() as c:
            if self.pg:
                c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            c.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS jobs (id VARCHAR(64) PRIMARY KEY, source VARCHAR(128) NOT NULL, external_id VARCHAR(128) NOT NULL, content_hash VARCHAR(64) NOT NULL, payload TEXT NOT NULL, searchable TEXT NOT NULL, embedding {vector_type} NOT NULL, model VARCHAR(200) NOT NULL, active INTEGER NOT NULL, updated_at VARCHAR(40) NOT NULL, UNIQUE(source,external_id))"
                )
            )
            c.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS jobs_source_active ON jobs(source,active)"
                )
            )
            if self.pg:
                c.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS jobs_fts ON jobs USING gin(to_tsvector('english',searchable))"
                    )
                )
            c.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS source_runs (id VARCHAR(64) PRIMARY KEY, source VARCHAR(128), stats TEXT, created_at VARCHAR(40))"
                )
            )
            c.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS index_state (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL)"
                )
            )
            c.execute(
                text(
                    "INSERT INTO index_state (id,revision) VALUES (1,0) ON CONFLICT (id) DO NOTHING"
                )
            )
            c.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS saved_searches (id VARCHAR(64) PRIMARY KEY, query TEXT NOT NULL)"
                )
            )
            c.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS feedback_events (id VARCHAR(64) PRIMARY KEY, job_id VARCHAR(64), useful INTEGER)"
                )
            )
            schema.upgrade(c)
            if self.pg:
                c.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS jobs_fixture_hnsw ON jobs USING hnsw ((embedding::vector(64)) vector_cosine_ops) WHERE model='fixture-hash-v1'"
                    )
                )
                c.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS jobs_minilm_hnsw ON jobs USING hnsw ((embedding::vector(384)) vector_cosine_ops) WHERE model='sentence-transformers/all-MiniLM-L6-v2'"
                    )
                )

    def revision(self):
        with self.engine.connect() as c:
            return c.execute(
                text("SELECT revision FROM index_state WHERE id=1")
            ).scalar_one()

    def ingest(self, source, postings, full_snapshot=False):
        from uuid import uuid4

        validated = [Posting.model_validate(p) for p in postings]
        if len({p.external_id for p in validated}) != len(validated):
            raise ValueError("Duplicate external IDs in snapshot")
        stats = {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "deactivated": 0,
            "embeddings": 0,
        }
        stamp = datetime.now(timezone.utc).isoformat()
        seen = set()
        with self.engine.begin() as c:
            # Serialize writers to keep snapshots and revision invalidation atomic on PostgreSQL.
            if self.pg:
                c.execute(
                    text("SELECT revision FROM index_state WHERE id=1 FOR UPDATE")
                )
            c.execute(
                text(
                    "INSERT INTO sources (id,adapter,config,interval_seconds,last_attempt,last_success) VALUES (:id,'local','{}',3600,:stamp,:stamp) ON CONFLICT(id) DO UPDATE SET last_attempt=:stamp,last_success=:stamp"
                ),
                {"id": source, "stamp": stamp},
            )
            for p in validated:
                identity = hashlib.sha256(
                    (source + "\0" + p.external_id).encode()
                ).hexdigest()
                seen.add(identity)
                old = (
                    c.execute(
                        text("SELECT content_hash,model,active FROM jobs WHERE id=:id"),
                        {"id": identity},
                    )
                    .mappings()
                    .first()
                )
                identity_text = "|".join(
                    " ".join(v.lower().split())
                    for v in [p.employer, p.title, p.location, p.description]
                )
                canonical = hashlib.sha256(identity_text.encode()).hexdigest()
                c.execute(
                    text(
                        "INSERT INTO canonical_jobs VALUES (:id,:identity,:stamp) ON CONFLICT(id) DO NOTHING"
                    ),
                    {"id": canonical, "identity": identity_text, "stamp": stamp},
                )
                changed = (
                    not old
                    or old["content_hash"] != digest(p)
                    or old["model"] != self.embedder.version
                )
                if not changed and old["active"]:
                    c.execute(
                        text(
                            "INSERT INTO job_postings VALUES (:id,:source,:canonical,:stamp,:stamp,'active') ON CONFLICT(id) DO UPDATE SET canonical_id=:canonical,last_seen=:stamp,status='active'"
                        ),
                        {
                            "id": identity,
                            "source": source,
                            "canonical": canonical,
                            "stamp": stamp,
                        },
                    )
                    stats["unchanged"] += 1
                    continue
                embedding_hash = hashlib.sha256(content(p).encode()).hexdigest()
                prior = c.execute(
                    text(
                        "SELECT vector_json FROM embedding_versions WHERE content_hash=:h AND model=:m"
                    ),
                    {"h": embedding_hash, "m": self.embedder.version},
                ).scalar()
                if prior:
                    embedding = json.loads(prior)
                else:
                    embedding = self.embedder.encode(content(p))
                    stats["embeddings"] += 1
                    eid = hashlib.sha256(
                        (embedding_hash + self.embedder.version).encode()
                    ).hexdigest()
                    c.execute(
                        text(
                            "INSERT INTO embedding_versions VALUES (:id,:h,:m,:dim,:vec,:stamp) ON CONFLICT(id) DO NOTHING"
                        ),
                        {
                            "id": eid,
                            "h": embedding_hash,
                            "m": self.embedder.version,
                            "dim": len(embedding),
                            "vec": json.dumps(embedding),
                            "stamp": stamp,
                        },
                    )
                params = {
                    "id": identity,
                    "source": source,
                    "external_id": p.external_id,
                    "hash": digest(p),
                    "payload": json.dumps(p.model_dump()),
                    "searchable": content(p),
                    "embedding": json.dumps(embedding),
                    "model": self.embedder.version,
                    "stamp": stamp,
                }
                value = "CAST(:embedding AS vector)" if self.pg else ":embedding"
                c.execute(
                    text(
                        f"INSERT INTO jobs VALUES (:id,:source,:external_id,:hash,:payload,:searchable,{value},:model,1,:stamp) ON CONFLICT(id) DO UPDATE SET content_hash=excluded.content_hash,payload=excluded.payload,searchable=excluded.searchable,embedding=excluded.embedding,model=excluded.model,active=1,updated_at=excluded.updated_at"
                    ),
                    params,
                )
                c.execute(
                    text(
                        "INSERT INTO job_postings VALUES (:id,:source,:canonical,:stamp,:stamp,'active') ON CONFLICT(id) DO UPDATE SET canonical_id=:canonical,last_seen=:stamp,status='active'"
                    ),
                    {
                        "id": identity,
                        "source": source,
                        "canonical": canonical,
                        "stamp": stamp,
                    },
                )
                stats["updated" if old else "created"] += 1
            if full_snapshot:
                rows = (
                    c.execute(
                        text("SELECT id FROM jobs WHERE source=:source AND active=1"),
                        {"source": source},
                    )
                    .scalars()
                    .all()
                )
                for identity in rows:
                    if identity not in seen:
                        c.execute(
                            text(
                                "UPDATE jobs SET active=0,updated_at=:stamp WHERE id=:id"
                            ),
                            {"id": identity, "stamp": stamp},
                        )
                        stats["deactivated"] += 1
                        c.execute(
                            text(
                                "UPDATE job_postings SET status='inactive' WHERE id=:id"
                            ),
                            {"id": identity},
                        )
            if stats["created"] + stats["updated"] + stats["deactivated"]:
                c.execute(text("UPDATE index_state SET revision=revision+1 WHERE id=1"))
            c.execute(
                text("INSERT INTO source_runs VALUES (:id,:source,:stats,:stamp)"),
                {
                    "id": str(uuid4()),
                    "source": source,
                    "stats": json.dumps(stats),
                    "stamp": stamp,
                },
            )
        self.local_cache.clear()
        return stats

    def jobs(self):
        with self.engine.connect() as c:
            return [
                {
                    **json.loads(r["payload"]),
                    "id": r["id"],
                    "updated_at": r["updated_at"],
                    "canonical_id": r["canonical_id"],
                    "first_seen": r["first_seen"],
                    "last_seen": r["last_seen"],
                }
                for r in c.execute(
                    text(
                        "SELECT j.*,p.canonical_id,p.first_seen,p.last_seen FROM jobs j LEFT JOIN job_postings p ON p.id=j.id WHERE j.active=1 ORDER BY j.id"
                    )
                ).mappings()
            ]

    def search(
        self,
        query,
        mode="hybrid",
        location="",
        remote=False,
        skills=(),
        k=60,
        limit=20,
        offset=0,
        seniority="",
        weights=None,
    ):
        started = time.perf_counter()
        key = (
            "delta:"
            + self.embedder.version
            + ":"
            + str(self.revision())
            + ":"
            + hashlib.sha256(
                json.dumps(
                    [
                        query.lower().strip(),
                        mode,
                        location,
                        remote,
                        sorted(skills),
                        k,
                        limit,
                        offset,
                        seniority,
                        weights,
                    ]
                ).encode()
            ).hexdigest()
        )
        cached = self.cache.get(key) if self.cache else self.local_cache.get(key)
        if cached:
            payload = {**json.loads(cached), "cache": "hit"}
            self.record_retrieval(query, mode, payload, started)
            return payload
        all_jobs = self.jobs()
        eligible = {
            j["id"]: j
            for j in all_jobs
            if (not location or location.lower() in j["location"].lower())
            and (not remote or j["remote"])
        }
        if self.pg:
            with self.engine.connect() as c:
                lex = (
                    c.execute(
                        text(
                            "SELECT id,ts_rank_cd(to_tsvector('english',searchable),plainto_tsquery('english',:q)) AS score FROM jobs WHERE active=1 AND to_tsvector('english',searchable) @@ plainto_tsquery('english',:q) ORDER BY score DESC,id"
                        ),
                        {"q": query},
                    )
                    .mappings()
                    .all()
                )
                vec = (
                    c.execute(
                        text(
                            "SELECT id,1-(embedding <=> CAST(:v AS vector)) AS score FROM jobs WHERE active=1 AND model=:model ORDER BY score DESC,id"
                        ),
                        {
                            "v": json.dumps(self.embedder.encode(query)),
                            "model": self.embedder.version,
                        },
                    )
                    .mappings()
                    .all()
                )
        else:
            q = set(tokens(query))
            v = self.embedder.encode(query)
            lex = sorted(
                [
                    {
                        "id": j["id"],
                        "score": len(
                            q
                            & set(
                                tokens(
                                    " ".join(
                                        [j["title"], j["description"], *j["skills"]]
                                    )
                                )
                            )
                        ),
                    }
                    for j in all_jobs
                ],
                key=lambda r: (-r["score"], r["id"]),
            )
            lex = [r for r in lex if r["score"] > 0]
            with self.engine.connect() as c:
                rows = (
                    c.execute(text("SELECT id,embedding FROM jobs WHERE active=1"))
                    .mappings()
                    .all()
                )
            vec = sorted(
                [
                    {
                        "id": r["id"],
                        "score": sum(
                            a * b for a, b in zip(v, json.loads(r["embedding"]))
                        ),
                    }
                    for r in rows
                ],
                key=lambda r: (-r["score"], r["id"]),
            )
        lex = [r for r in lex if r["id"] in eligible]
        vec = [r for r in vec if r["id"] in eligible]
        lr = {r["id"]: i + 1 for i, r in enumerate(lex)}
        vr = {r["id"]: i + 1 for i, r in enumerate(vec)}
        fused = (
            rrf([list(lr), list(vr)], k)
            if mode == "hybrid"
            else {
                r["id"]: float(r["score"]) for r in (lex if mode == "keyword" else vec)
            }
        )
        results = []
        for identity, base in fused.items():
            job = eligible[identity]
            features = preferences(job, skills, remote, location, seniority, weights)
            results.append(
                {
                    "job": job,
                    "lexical_rank": lr.get(identity),
                    "vector_rank": vr.get(identity),
                    "base_score": base,
                    "preferences": features,
                    "score": base + sum(features.values()),
                }
            )
        results.sort(key=lambda r: (-r["score"], r["job"]["id"]))
        unique = []
        seen = set()
        for row in results:
            canonical = row["job"].get("canonical_id") or row["job"]["id"]
            if canonical not in seen:
                unique.append(row)
                seen.add(canonical)
        results = unique
        payload = {
            "results": results[offset : offset + limit],
            "total": len(results),
            "mode": mode,
            "embedding_model": self.embedder.version,
            "lexical_engine": "PostgreSQL ts_rank_cd"
            if self.pg
            else "native test token overlap",
            "cache": "miss",
        }
        if self.cache:
            self.cache.set(key, json.dumps(payload), ex=120)
        else:
            if len(self.local_cache) >= 256:
                self.local_cache.pop(next(iter(self.local_cache)))
            self.local_cache[key] = json.dumps(payload)
        self.record_retrieval(query, mode, payload, started)
        return payload

    def record_retrieval(self, query, mode, payload, started):
        with self.engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO retrieval_events VALUES (:id,:q,:mode,:revision,:count,:elapsed,:cache,:stamp)"
                ),
                {
                    "id": str(uuid4()),
                    "q": query,
                    "mode": mode,
                    "revision": self.revision(),
                    "count": payload["total"],
                    "elapsed": (time.perf_counter() - started) * 1000,
                    "cache": payload["cache"],
                    "stamp": datetime.now(timezone.utc).isoformat(),
                },
            )

    def deactivate_stale(self, cutoff):
        with self.engine.begin() as c:
            if self.pg:
                c.execute(
                    text("SELECT revision FROM index_state WHERE id=1 FOR UPDATE")
                )
            ids = (
                c.execute(
                    text(
                        "SELECT id FROM job_postings WHERE last_seen<:cutoff AND status='active'"
                    ),
                    {"cutoff": cutoff},
                )
                .scalars()
                .all()
            )
            for identity in ids:
                c.execute(
                    text("UPDATE jobs SET active=0 WHERE id=:id"), {"id": identity}
                )
                c.execute(
                    text("UPDATE job_postings SET status='stale' WHERE id=:id"),
                    {"id": identity},
                )
            if ids:
                c.execute(text("UPDATE index_state SET revision=revision+1 WHERE id=1"))
        return len(ids)

    def run_source(self, source):
        from .adapters import greenhouse

        with self.engine.connect() as c:
            row = (
                c.execute(text("SELECT * FROM sources WHERE id=:id"), {"id": source})
                .mappings()
                .first()
            )
        if not row:
            raise ValueError("Source not found")
        try:
            config = json.loads(row["config"])
            if row["adapter"] != "greenhouse":
                raise ValueError(
                    "Only registered Greenhouse sources can be fetched remotely"
                )
            return self.ingest(source, greenhouse(config["board"]), True)
        except Exception as error:
            with self.engine.begin() as c:
                c.execute(
                    text(
                        "INSERT INTO ingestion_failures VALUES (:id,:source,:error,1,:stamp)"
                    ),
                    {
                        "id": str(uuid4()),
                        "source": source,
                        "error": type(error).__name__,
                        "stamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                c.execute(
                    text("UPDATE sources SET last_attempt=:stamp WHERE id=:source"),
                    {"stamp": datetime.now(timezone.utc).isoformat(), "source": source},
                )
            raise
