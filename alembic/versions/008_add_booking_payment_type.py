"""Add booking_payment_type to items

Revision ID: 008
Revises: 007
Create Date: 2026-04-11 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('items', sa.Column('booking_payment_type', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('items', 'booking_payment_type')
