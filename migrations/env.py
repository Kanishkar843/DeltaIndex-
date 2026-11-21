import os
from sqlalchemy import create_engine
from alembic import context
engine=create_engine(os.getenv('DATABASE_URL','sqlite:///./deltaindex.db'))
with engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():context.run_migrations()
