import argparse, time, json
from datetime import datetime, timezone
from sqlalchemy import text
from .store import Index
from .adapters import local_file

p = argparse.ArgumentParser()
sub = p.add_subparsers(dest="command", required=True)
ingest = sub.add_parser("ingest")
ingest.add_argument("path")
ingest.add_argument("--source", default="local")
ingest.add_argument("--snapshot", action="store_true")
scheduler = sub.add_parser("schedule")
scheduler.add_argument("--once", action="store_true")
stale = sub.add_parser("expire")
stale.add_argument("--before", required=True)
a = p.parse_args()
index = Index()
index.migrate()
if a.command == "ingest":
    print(json.dumps(index.ingest(a.source, local_file(a.path), a.snapshot)))
elif a.command == "expire":
    datetime.fromisoformat(a.before)
    print({"deactivated": index.deactivate_stale(a.before)})
else:
    while True:
        with index.engine.connect() as c:
            rows = (
                c.execute(text("SELECT * FROM sources WHERE adapter='greenhouse'"))
                .mappings()
                .all()
            )
        for row in rows:
            stamp = row["last_attempt"]
            due = (
                not stamp
                or (
                    datetime.now(timezone.utc) - datetime.fromisoformat(stamp)
                ).total_seconds()
                >= row["interval_seconds"]
            )
            if due:
                try:
                    print(
                        json.dumps(
                            {"source": row["id"], "result": index.run_source(row["id"])}
                        )
                    )
                except Exception as error:
                    print(
                        json.dumps(
                            {"source": row["id"], "failure": type(error).__name__}
                        )
                    )
        if a.once:
            break
        time.sleep(30)
