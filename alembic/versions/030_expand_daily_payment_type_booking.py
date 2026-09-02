"""expand daily_payments.type check to include booking

Revision ID: 030_expand_daily_payment_type
Revises: 029_drop_sales_item_id_fk
Create Date: 2026-09-02

Zero-downtime: DROP CONSTRAINT IF EXISTS + ADD CONSTRAINT.
Does not touch data. Needed because preorder/booking path writes type='booking'.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "030_expand_daily_payment_type"
down_revision: Union[str, None] = "029_drop_sales_item_id_fk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Имя constraint из модели: type_check
    op.execute(
        "ALTER TABLE daily_payments DROP CONSTRAINT IF EXISTS type_check"
    )
    op.execute(
        """
        ALTER TABLE daily_payments
        ADD CONSTRAINT type_check
        CHECK (type IN ('sale', 'preorder', 'booking'))
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE daily_payments DROP CONSTRAINT IF EXISTS type_check"
    )
    op.execute(
        """
        ALTER TABLE daily_payments
        ADD CONSTRAINT type_check
        CHECK (type IN ('sale', 'preorder'))
        """
    )
