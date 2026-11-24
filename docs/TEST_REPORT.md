# Executed acceptance report

Updated 2026-11-22. Later results supersede the initial static native demo.

| Check | Actual result |
|---|---|
| `python -m pytest -q tests` | PASS: 11 tests, 11.32 seconds |
| `python -m pytest -q integration` | PASS: 1 real PostgreSQL/pgvector + Redis test, 2.81 seconds |
| TypeScript typecheck / ESLint | PASS |
| Vitest | PASS: 2 tests |
| Vite production build | PASS |
| Ruff selected correctness rules | PASS |
| Chrome React browser journey | PASS; desktop/light/mobile screenshots captured |
| Actual MiniLM encoding | PASS: 384 dimensions, normalized vector |
| Real model retrieval benchmark | PASS; six cases, three modes, with/without preferences, raw samples recorded |
| Docker build/start/restart | PASS: healthy PostgreSQL/pgvector + Redis + API, 120-job idempotence and persisted jobs after API restart |
| Live Greenhouse board | NOT RUN; bounded adapter retry/failure tests use mocked transport |
| GitHub CI/publication | Feature branch and PR published; corrected CI runs passed |

The integration test applies Alembic, verifies pgvector, inserts/reingests, changes one description, verifies exactly one embedding refresh, verifies metadata-only vector reuse, Redis miss/hit/invalidation, canonical dedup, three retrieval modes, SQL-injection-resistant filtering and stale deactivation. PostgreSQL 17.12 and pgvector 0.8.7 are native binaries. Redis 8.10.3 is a community Windows build, not official Redis distribution. Docker checks will use Linux images separately.

Browser coverage: rejected missing token, connection, ingestion of 120 listings, unchanged reingestion, retrieval, score drawer, feedback, saved searches, profiles, three-mode comparison, empty results and responsive themes. The browser fixture uses SQLite/hash vectors; it is not reported as PostgreSQL/model integration. Initial browser attempts failed for missing Playwright, then an obsolete theme selector; both were corrected before the passing run.

Managed Python's OpenSSL downloader crashed. Actual model execution succeeded using pinned, checksum-verified local model files with offline loading; TLS verification was never disabled. The initial three-case benchmark was expanded because its easy labels did not assess preference effects. The six-case artifact is the current benchmark authority. See BENCHMARK.md for limitations.

Docker acceptance uses fixture vectors with real pgvector and Redis; native benchmark separately verifies actual MiniLM inference. See docker-test-output.txt. No live provider or optional Docker-model image result is implied.

GitHub CI first failed because the browser harness assumed an ignored .cache directory existed. The harness now creates its log directory on clean checkouts. This was a CI setup failure, not a passing browser result; the corrected run is tracked separately.

Published branch: `feat/verified-hybrid-react`; [PR](https://github.com/Kanishkar843/DeltaIndex-/pull/1), [Actions](https://github.com/Kanishkar843/DeltaIndex-/actions). Existing remote main is an ancestor of the delivered branch. No force push or main overwrite occurred.

## Production verification — 2026-11-24

See [CLOUD_DELIVERY](CLOUD_DELIVERY.md) for actual Vercel, Neon, provider, browser and model results. Earlier local results above retain their original scope.
