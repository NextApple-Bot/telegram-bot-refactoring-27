"""change sale_message_id columns to bigint

Revision ID: 023
Revises: 022
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('daily_payments', 'sale_message_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=True)

    op.alter_column('sales', 'message_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=True)

    op.alter_column('deleted_items', 'sale_message_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=True)


def downgrade():
    op.alter_column('daily_payments', 'sale_message_id', type_=sa.Integer())
    op.alter_column('sales', 'message_id', type_=sa.Integer())
    op.alter_column('deleted_items', 'sale_message_id', type_=sa.Integer())
