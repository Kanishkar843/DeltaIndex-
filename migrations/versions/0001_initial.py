from app.store import Index
revision='0001'
down_revision=None
branch_labels=None
depends_on=None
def upgrade(): Index().migrate()
def downgrade(): raise RuntimeError('Destructive downgrade is intentionally unsupported; restore a backup')
