"""Add functional index on normalized serial number

Revision ID: 010
Revises: 009
Create Date: 2026-04-15 12:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_items_serial_normalized
        ON items (regexp_replace(serial, '[№\\s]', '', 'g'))
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_items_serial_normalized")
