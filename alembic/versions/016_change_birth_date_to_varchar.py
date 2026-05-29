"""Change birth_date type to VARCHAR

Revision ID: 016
Revises: 015
Create Date: 2026-04-29 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
        ALTER TABLE clients ALTER COLUMN birth_date TYPE VARCHAR USING birth_date::varchar
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE clients ALTER COLUMN birth_date TYPE DATE USING birth_date::date
    """)
