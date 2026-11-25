# Measured retrieval benchmark

Executed 2026-11-22 on Windows 11 / Intel Core 7 150U / 16GB RAM. Actual CPU Sentence Transformers all-MiniLM-L6-v2, PostgreSQL 17.12 + pgvector 0.8.7 and Redis 8.10.3. 120 synthetic listings; six explicit labeled cases (three specific queries and three ambiguous engineer queries with skill/seniority personas). Labels are authored against the synthetic taxonomy, not external human relevance judgments.

| Mode | Personalized | Mean Recall@10 | Mean nDCG@10 |
|---|---|---:|---:|
| keyword | False | 0.2917 | 0.5982 |
| keyword | True | 0.5000 | 1.0000 |
| semantic | False | 0.3167 | 0.6325 |
| semantic | True | 0.3333 | 0.6667 |
| hybrid | False | 0.2833 | 0.5631 |
| hybrid | True | 0.4833 | 0.9675 |

Cached latency: 180 samples, p50 12.89ms, p95 20.73ms. These are in-process search timings including Redis and PostgreSQL retrieval-event writes, not HTTP/browser latency. Cache-miss timings are individually recorded in benchmark-results.json. Model startup is excluded from query latency.

Peak process working set: 462.27 MiB. Whole benchmark wall time: 55.85s; process CPU time: 31.61s. Memory excludes PostgreSQL, Redis, Docker, browser and other processes. A Docker dependency build was active during measurement; results are not isolated-machine performance claims.

Reproduce using an isolated PostgreSQL database and dedicated Redis database selected through BENCHMARK_DATABASE_URL / BENCHMARK_REDIS_URL, then `python -m app.benchmark --mode sentence-transformers --repeats 5`. MODEL_PATH can select the verified local model folder; HF_HUB_OFFLINE=1 disables model downloads. The benchmark creates its schema and ingests the synthetic corpus; never target production data. Data and qrels SHA-256, versions, per-query scores, top IDs, and raw latency samples are in benchmark-results.json.

Model revision: `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; safetensors SHA-256: `53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db`. Verified against Hugging Face API metadata. Model card specifies Apache-2.0; model files/card stay in the external ignored cache, not Git. A native managed-Python OpenSSL download crash was bypassed by verified local-file loading, without disabling TLS.

The small templated corpus is easy and cannot establish production retrieval quality. Recall@10 cannot exceed .5 when a case has 20 relevant documents. No ANN scaling, live jobs, LLM judgments or user engagement measurements are claimed.
