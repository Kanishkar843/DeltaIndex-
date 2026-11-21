from alembic import op
import sqlalchemy as sa
revision="0001"
down_revision=None
branch_labels=None
depends_on=None
STATEMENTS=['CREATE TABLE jobs (id VARCHAR(64) PRIMARY KEY, source VARCHAR(128) NOT NULL, external_id VARCHAR(128) NOT NULL, content_hash VARCHAR(64) NOT NULL, payload TEXT NOT NULL, searchable TEXT NOT NULL, embedding {vector_type} NOT NULL, model VARCHAR(200) NOT NULL, active INTEGER NOT NULL, updated_at VARCHAR(40) NOT NULL, UNIQUE(source,external_id))', 'CREATE INDEX jobs_source_active ON jobs(source,active)', 'CREATE TABLE source_runs (id VARCHAR(64) PRIMARY KEY, source VARCHAR(128), stats TEXT, created_at VARCHAR(40))', 'CREATE TABLE index_state (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL)', 'INSERT INTO index_state VALUES (1,0)', 'CREATE TABLE saved_searches (id VARCHAR(64) PRIMARY KEY, query TEXT NOT NULL)', 'CREATE TABLE feedback_events (id VARCHAR(64) PRIMARY KEY, job_id VARCHAR(64), useful INTEGER)']
def upgrade():
    c=op.get_bind();pg=c.dialect.name=='postgresql'
    if pg:c.execute(sa.text('CREATE EXTENSION IF NOT EXISTS vector'))
    for statement in STATEMENTS:c.execute(sa.text(statement.format(vector_type='vector' if pg else 'TEXT')))
    if pg:c.execute(sa.text("CREATE INDEX jobs_fts ON jobs USING gin(to_tsvector('english',searchable))"))
def downgrade():
    for table in ['feedback_events','saved_searches','index_state','source_runs','jobs']:op.drop_table(table)
