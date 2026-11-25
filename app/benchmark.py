"""Measured retrieval benchmark; requires explicitly selected isolated services."""

import argparse, hashlib, json, os, statistics, time
from pathlib import Path
import psutil
from .store import Index
from .core import recall, ndcg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=["fixture", "sentence-transformers"], default="fixture"
    )
    parser.add_argument("--output", default="docs/benchmark-results.json")
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    assert 1 <= args.repeats <= 100
    url = os.environ.get("BENCHMARK_DATABASE_URL", "")
    redis_url = os.environ.get("BENCHMARK_REDIS_URL", "")
    assert url.startswith("postgresql") and redis_url.startswith("redis://"), (
        "Explicit isolated PostgreSQL and Redis required"
    )
    process = psutil.Process()
    cpu0 = process.cpu_times()
    start = time.perf_counter()
    idx = Index(url, args.mode, redis_url)
    idx.migrate()
    data = Path("data/jobs.json").read_bytes()
    ingest = idx.ingest("benchmark", json.loads(data), True)
    qrels = Path("evals/relevance_qrels.jsonl").read_bytes()
    cases = [json.loads(line) for line in qrels.decode().splitlines() if line.strip()]
    rows = []
    for mode in ("keyword", "semantic", "hybrid"):
        for personalized in (False, True):
            for case in cases:
                options = case.get("preferences", {}) if personalized else {}
                # Delete only this model's benchmark cache keys, never FLUSHDB.
                keys = list(idx.cache.scan_iter("delta:" + idx.embedder.version + ":*"))
                if keys:
                    idx.cache.delete(*keys)
                began = time.perf_counter()
                result = idx.search(case["query"], mode, limit=100, **options)
                cold = (time.perf_counter() - began) * 1000
                ranked = [r["job"]["external_id"] for r in result["results"]]
                relevant = (
                    case.get(
                        "personalized_relevant_external_ids",
                        case["relevant_external_ids"],
                    )
                    if personalized
                    else case["relevant_external_ids"]
                )
                samples = []
                for _ in range(args.repeats):
                    began = time.perf_counter()
                    cached = idx.search(case["query"], mode, limit=100, **options)
                    samples.append((time.perf_counter() - began) * 1000)
                    assert cached["cache"] == "hit"
                rows.append(
                    {
                        "mode": mode,
                        "personalized": personalized,
                        "query": case["query"],
                        "recall_at_10": recall(ranked, relevant, 10),
                        "ndcg_at_10": ndcg(ranked, relevant, 10),
                        "cold_ms": cold,
                        "cache_samples_ms": samples,
                        "top_external_ids": ranked[:10],
                    }
                )
    samples = [v for r in rows for v in r["cache_samples_ms"]]
    cpu = process.cpu_times()
    elapsed = time.perf_counter() - start
    with idx.engine.connect() as c:
        from sqlalchemy import text

        pg = c.execute(text("SELECT version()")).scalar()
        vector = c.execute(
            text("SELECT extversion FROM pg_extension WHERE extname='vector'")
        ).scalar()
    report = {
        "embedding_model": idx.embedder.version,
        "postgres": pg,
        "pgvector": vector,
        "redis": idx.cache.info("server")["redis_version"],
        "dataset_sha256": hashlib.sha256(data).hexdigest(),
        "qrels_sha256": hashlib.sha256(qrels).hexdigest(),
        "dataset_size": len(json.loads(data)),
        "ingest": ingest,
        "results": rows,
        "cached_sample_count": len(samples),
        "cached_p50_ms": statistics.median(samples),
        "cached_p95_ms": sorted(samples)[
            max(0, __import__("math").ceil(0.95 * len(samples)) - 1)
        ],
        "process_rss_bytes_end": process.memory_info().rss,
        "process_peak_working_set_bytes": getattr(
            process.memory_info(), "peak_wset", None
        ),
        "wall_seconds": elapsed,
        "process_cpu_seconds": cpu.user + cpu.system - cpu0.user - cpu0.system,
        "limitations": "Synthetic templated labels, small corpus, single process, warm OS/model; cache latency includes retrieval-event SQL write. Not production traffic or external relevance judgments.",
    }
    Path(args.output).write_text(json.dumps(report, indent=2))
    idx.engine.dispose()
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ("results", "postgres")},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
