from alembic import context
from app.store import Index
index=Index()
with index.engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction(): context.run_migrations()
