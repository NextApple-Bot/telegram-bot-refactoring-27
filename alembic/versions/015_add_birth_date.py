"""Add birth_date to clients

Revision ID: 015
Revises: 014
Create Date: 2026-04-29 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('clients', sa.Column('birth_date', sa.Date(), nullable=True))

def downgrade() -> None:
    op.drop_column('clients', 'birth_date')
