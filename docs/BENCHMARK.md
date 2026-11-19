# Executed fixture benchmark

Command: `python -m app.benchmark`. Raw output: benchmark-results.json.

120 synthetic postings, three queries, 20 relevant postings per query. All three tested modes scored Recall@10=0.5 and nDCG@10=1.0 for all three queries. Recall cannot exceed 0.5 at ten results when twenty documents are relevant. These easy, repetitive fixtures verify metric wiring and rank behavior, not practical retrieval quality. Environment: native SQLite and deterministic hash embeddings. PostgreSQL ranking and Sentence Transformers are NOT tested by these numbers. No p95, throughput or production relevance claims.
