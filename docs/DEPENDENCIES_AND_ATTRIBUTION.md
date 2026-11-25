# Dependencies and attribution

Original first-party Python, HTML, CSS, JavaScript, fixtures, tests and documentation were authored in this run. The projects share original CSS primitives authored for this assignment. No application template, external repository code, logos, stock images or copied dashboard was used. UI screenshots are generated from the local applications. Unicode marks and system fonts require no downloaded font or icon assets.

Resolved packages are pinned in requirements.lock. Runtime/dev packages include FastAPI, Starlette, Pydantic, Uvicorn, SQLAlchemy, Alembic, psycopg, pytest and HTTPX. PrefLoom adds LangGraph; DeltaIndex adds Redis and pgvector clients with optional Sentence Transformers; EvalTrace adds jsonschema. Playwright is browser-test tooling. Installed package license metadata and notices remain in their distributions; do not strip them when redistributing. There is no first-party LICENSE pending owner selection. Docker base images and PostgreSQL/Redis retain their own licenses. Optional model weights require review of their model card/license before distribution.

Official documentation consulted for API patterns:
- https://reference.langchain.com/python/langgraph/graph/state/StateGraph
- https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html

No nontrivial tutorial implementation was copied. This list is not a legal audit; consult each installed distribution's license files. A generated package inventory is recorded in dependencies.json when available.

React, React DOM, TypeScript, Vite, Vitest and ESLint frontend dependencies are pinned in frontend/package-lock.json. CSS and UI implementation are original, sharing only first-party primitives with PrefLoom. all-MiniLM-L6-v2's model card declares Apache-2.0; its exact revision and verified safetensors checksum are in BENCHMARK.md, and files/card are retained in the ignored model cache. No weights are redistributed through Git. Native PostgreSQL acceptance uses pgvector built from its official dependency source, not application code. Windows Redis is the community redis-windows distribution (https://github.com/redis-windows/redis-windows), used only for local development; Docker uses official Redis Linux images. Original distribution notices remain intact. Greenhouse read-only endpoint documentation was checked at https://docs.greenhouse.io/job-board.html.

Cloud inference adds ONNX Runtime (MIT), NumPy (BSD) and Tokenizers (Apache-2.0). MiniLM quantized ONNX weights retain the upstream Apache-2.0 model card in the deployed model directory. Revision: 1110a243fdf4706b3f48f1d95db1a4f5529b4d41. ONNX SHA256: b941bf19f1f1283680f449fa6a7336bb5600bdcd5f84d10ddc5cd72218a0fd21. Weights are downloaded from the official model repository and excluded from Git.
