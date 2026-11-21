# Windows, WSL and Docker

Python 3.12 and Node 22 commands are in README. Native default is SQLite fixture mode. For PostgreSQL set DATABASE_URL, use a dedicated REDIS_URL database, and apply `python -m alembic upgrade head`. PostgreSQL requires pgvector installed server-side, not only the Python pgvector package.

WSL and Docker are now installed with prior authorization; no automatic Windows reboot was performed. Compose limits PostgreSQL to 512MB, Redis to 128MB and API to 768MB. Only the API has a loopback host port (8001, or APP_PORT); services stay on the private Compose network. Set POSTGRES_PASSWORD and ADMIN_TOKEN using ignored local environment configuration. Run one project at a time.

```powershell
docker compose up --build -d --wait
$env:ACCEPTANCE_URL='http://127.0.0.1:8001'
$env:COMPOSE_PROJECT_NAME='deltaindex'
python tests/compose_acceptance.py
docker compose down
```

Set COMPOSE_PROJECT_NAME consistently before startup and verification. The acceptance script creates synthetic data and restarts only that test project's API. Never run it against production. Omit `-v` to preserve volumes. On enterprise-certificate networks, use external public roots through BUILD_CA_FILE and `-f compose.yaml -f compose.trust.yaml`; this is a BuildKit secret, not an instruction to disable TLS.

## CPU model mode

Native CPU torch and Sentence Transformers are already installed on the inspected machine. For a fresh environment:

```powershell
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0+cpu
python -m pip install -r requirements-model.txt
$env:EMBEDDING_MODE='sentence-transformers'
```

Model revision is pinned in core.py. Set MODEL_PATH to an existing verified MiniLM folder and HF_HUB_OFFLINE=1 for network-free model loading. The current machine uses K:/Projects/DeltaIndex/.cache/models/minilm-local. This avoids a managed-Python OpenSSL download crash without weakening certificate verification. Model card and checksum are recorded in BENCHMARK.md. Weight files are not in Git.

Docker's default image intentionally uses fixtures. Dockerfile.model is an optional extension: tag the built API image as `deltaindex-api:local`, build the extension, then select it with EMBEDDING_MODE=sentence-transformers and a writable model cache. That optional model image has NOT been executed; native real-model benchmark results do not establish Docker-model success.

Windows Redis acceptance used the community redis-windows build; Compose uses official Linux Redis. Neither native tests nor a successful image build alone establish startup/restart acceptance; see TEST_REPORT for current evidence.
