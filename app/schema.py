"""Additive relational entities used by ingestion, embeddings and retrieval."""

from sqlalchemy import text

DDL = [
    "CREATE TABLE IF NOT EXISTS sources (id VARCHAR(128) PRIMARY KEY, adapter VARCHAR(30) NOT NULL, config TEXT NOT NULL, interval_seconds INTEGER NOT NULL, last_attempt VARCHAR(40), last_success VARCHAR(40))",
    "CREATE TABLE IF NOT EXISTS canonical_jobs (id VARCHAR(64) PRIMARY KEY, identity_text TEXT NOT NULL, created_at VARCHAR(40) NOT NULL)",
    "CREATE TABLE IF NOT EXISTS job_postings (id VARCHAR(64) PRIMARY KEY REFERENCES jobs(id), source_id VARCHAR(128) NOT NULL REFERENCES sources(id), canonical_id VARCHAR(64) NOT NULL REFERENCES canonical_jobs(id), first_seen VARCHAR(40) NOT NULL, last_seen VARCHAR(40) NOT NULL, status VARCHAR(20) NOT NULL)",
    "CREATE INDEX IF NOT EXISTS postings_canonical ON job_postings(canonical_id,status)",
    "CREATE INDEX IF NOT EXISTS postings_seen ON job_postings(last_seen)",
    "CREATE TABLE IF NOT EXISTS embedding_versions (id VARCHAR(64) PRIMARY KEY, content_hash VARCHAR(64) NOT NULL, model VARCHAR(200) NOT NULL, dimensions INTEGER NOT NULL, vector_json TEXT NOT NULL, created_at VARCHAR(40) NOT NULL, UNIQUE(content_hash,model))",
    "CREATE TABLE IF NOT EXISTS profiles (id VARCHAR(64) PRIMARY KEY, preferences TEXT NOT NULL, updated_at VARCHAR(40) NOT NULL)",
    "CREATE TABLE IF NOT EXISTS retrieval_events (id VARCHAR(64) PRIMARY KEY, query TEXT NOT NULL, mode VARCHAR(20) NOT NULL, revision INTEGER NOT NULL, result_count INTEGER NOT NULL, elapsed_ms REAL NOT NULL, cache_status VARCHAR(20) NOT NULL, created_at VARCHAR(40) NOT NULL)",
    "CREATE TABLE IF NOT EXISTS ingestion_failures (id VARCHAR(64) PRIMARY KEY, source_id VARCHAR(128), error_type VARCHAR(100) NOT NULL, attempt INTEGER NOT NULL, created_at VARCHAR(40) NOT NULL)",
]


def upgrade(connection):
    for statement in DDL:
        connection.execute(text(statement))
