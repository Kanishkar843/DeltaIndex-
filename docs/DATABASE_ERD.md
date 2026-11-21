# Database schema

Alembic 0001 freezes jobs/source_runs/index_state/saved_searches/feedback_events. Revision 0002 adds lifecycle, profiles, embedding versions and retrieval/failure evidence. PostgreSQL enables vector and dimension-specific indexes; native SQLite stores fixture vectors as JSON text.

```mermaid
erDiagram
    sources ||--o{ job_postings : owns
    jobs ||--|| job_postings : lifecycle
    canonical_jobs ||--o{ job_postings : deduplicates
    sources ||--o{ source_runs : records
    sources ||--o{ ingestion_failures : records
    jobs {
        string id PK
        string source
        string external_id
        string content_hash
        vector embedding
        string model
        int active
    }
    job_postings {
        string id PK
        string source_id FK
        string canonical_id FK
        string first_seen
        string last_seen
        string status
    }
    embedding_versions {
        string id PK
        string content_hash
        string model
        int dimensions
        string vector_json
    }
    index_state {
        int id PK
        int revision
    }
    profiles {
        string id PK
        string preferences
    }
    retrieval_events {
        string id PK
        string query
        float elapsed_ms
        string cache_status
    }
    saved_searches {
        string id PK
        string query
    }
    feedback_events {
        string id PK
        string job_id
        int useful
    }
```

Source-run/failure links are logical source IDs; posting source/canonical/job links are enforced foreign keys. `(source,external_id)` and `(embedding text hash,model)` are unique. UTC ISO timestamps track lifecycle. Embedding text hashes exclude salary/URL metadata. The singleton revision row locks concurrent PostgreSQL ingestion and expires prior cache namespaces without deleting unrelated Redis data. Existing initial datasets acquire posting lifecycle entries when reingested.
