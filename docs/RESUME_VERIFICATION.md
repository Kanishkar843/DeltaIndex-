# Resume claim verification

| Claim | Implementation | Executed evidence |
|---|---|---|
| Incremental index, dedup and selective embedding refresh | app/store.py, schema.py, adapters.py | 11 tests + real PostgreSQL/Redis integration; 120-job benchmark |
| Relational SQL and pgvector over changing listings | frozen Alembic revisions, sources/canonical_jobs/job_postings/embedding_versions | Actual PG17.12 + pgvector0.8.7 test and benchmark |
| Full-text and semantic RRF retrieval | ts_rank_cd, cosine operator, Sentence Transformers MiniLM, core.rrf | Real 384-dimensional inference and six-case measured benchmark |
| Metadata filters and preference reranking | profile API, weighted score components | SQL filtering/injection test, persona labels and measured quality changes |
| Explainable matches | React score dialog and compare panels | Actual Chrome journey and screenshots |

Docker startup/restart passed; publication status is tracked in TEST_REPORT; a mocked public-source test is not live-feed evidence. Exact retrieval is implemented; do not claim ANN scaling or production quality from this small synthetic corpus.
