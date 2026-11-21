"""Test only an explicitly isolated, already started Compose stack."""

import json, os, subprocess, time, urllib.request

base = os.getenv("ACCEPTANCE_URL", "http://127.0.0.1:18081")
docker = os.getenv("DOCKER_BIN", "docker")
project = os.getenv("COMPOSE_PROJECT_NAME", "deltaindex-acceptance")
token = os.environ["ADMIN_TOKEN"]


def call(path, data=None):
    import httpx, ssl, truststore

    with httpx.Client(
        verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        trust_env=False,
        timeout=30,
    ) as client:
        response = client.request(
            "POST" if data is not None else "GET",
            base + path,
            json=data,
            headers={"Authorization": "Bearer " + token},
        )
        response.raise_for_status()
        return response.json()


health = call("/health")
assert health["database"] == "postgresql" and health["cache"] == "redis"
call("/ingest/seed", {})
assert call("/ingest/seed", {})["unchanged"] == 120
assert call("/search?q=python&mode=hybrid")["results"]
assert call("/search?q=python&mode=hybrid")["cache"] == "hit"
subprocess.run([docker, "compose", "-p", project, "restart", "api"], check=True)
for _ in range(90):
    try:
        call("/ready")
        break
    except Exception:
        time.sleep(1)
else:
    raise AssertionError("API did not recover")
assert len(call("/jobs?limit=100")) == 100
assert call("/ingest/seed", {})["unchanged"] == 120
print(
    json.dumps(
        {
            "postgres_pgvector": "passed",
            "redis_cache": "passed",
            "restart_persistence": "passed",
            "idempotent_120": "passed",
            "embedding_mode": health["embedding_mode"],
        }
    )
)
