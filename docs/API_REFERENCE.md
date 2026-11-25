# API reference

`/docs` and `/openapi.json` expose parameter schemas. Public GET routes: /health, /ready, /jobs, /search, /search/explain, /ingest/status, /ingest/freshness. Search takes q, mode (keyword/semantic/hybrid), location, remote, comma-separated skills, seniority, profile_id, k, limit and offset. Results expose raw ranks, base score, preference contributions, model, lexical engine and cache status.

Operator routes require `Authorization: Bearer <ADMIN_TOKEN>`: POST /ingest/run, POST /ingest/seed, GET/POST /profiles, GET/POST /saved-searches, POST /feedback, GET/POST /sources, POST /sources/{source_id}/run, GET /ingest/failures. Missing configuration returns 503; wrong credentials return 401. This is single-operator authentication, not user-session isolation.

Batch body: `{ "source": "local", "postings": [...], "full_snapshot": true }`. Source body: `{ "id": "my-board", "board": "approved-board-token", "interval_seconds": 3600 }`. Profile body accepts skills, remote, location, seniority and bounded weight mapping. Feedback body accepts job_id and useful. Invalid queries/payloads return 422; bounded remote-source failures return sanitized 502. Database parameters are bound, never concatenated from user filters.
