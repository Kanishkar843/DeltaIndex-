# Retrieval design

PostgreSQL lexical ranking uses `ts_rank_cd(to_tsvector(...), plainto_tsquery(...))`, not BM25. Vector ranking uses cosine distance through pgvector `<=>`. Hybrid score sums `1/(k+rank)` across lexical/vector lists. Missing ranks contribute zero. Default k=60. Filters apply to both lists before fusion. Preference contributions are 0.02 times requested-skill coverage and 0.01 for matching a requested remote preference. The returned result exposes both ranks, base score and feature contributions.

Native test mode substitutes token-overlap lexical ranking and deterministic 64-dimensional hashed vectors. This is not a semantic model. Real Sentence Transformers mode loads all-MiniLM-L6-v2 on CPU; it is implemented but untested. No embedding-model quality claim is supported by fixture results.

PostgreSQL GIN full-text and source/active B-tree indexes are implemented. ANN vector indexing and scale benchmarking remain pending. Redis keys contain the database revision; ingestion changes increment that revision transactionally, so old keys are unreachable and expire after 120 seconds. A query concurrent with ingestion can observe the preceding committed snapshot; the next query sees the new revision. Database failures fail the request rather than fabricating results.
