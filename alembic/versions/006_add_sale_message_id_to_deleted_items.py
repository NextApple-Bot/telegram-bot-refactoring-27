"""Add sale_message_id to deleted_items

Revision ID: 006
Revises: 005
Create Date: 2026-04-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('deleted_items', sa.Column('sale_message_id', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('deleted_items', 'sale_message_id')
