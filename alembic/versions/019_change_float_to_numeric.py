"""change float money columns to numeric(12,2)

Revision ID: 019
Revises: 018
Create Date: 2026-05-11 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '019'
down_revision = '018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # items
    for col in ['booking_price', 'booking_prepayment', 'sale_price', 'sale_prepayment',
                'sale_payment_amount', 'booking_bonus', 'sale_bonus', 'sale_change']:
        op.alter_column('items', col, type_=sa.Numeric(12,2),
                        postgresql_using=f'{col}::numeric(12,2)')
    # sales
    for col in ['cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment']:
        op.alter_column('sales', col, type_=sa.Numeric(12,2),
                        postgresql_using=f'{col}::numeric(12,2)')
    # preorders
    for col in ['cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment']:
        op.alter_column('preorders', col, type_=sa.Numeric(12,2),
                        postgresql_using=f'{col}::numeric(12,2)')
    # bookings
    op.alter_column('bookings', 'total_amount', type_=sa.Numeric(12,2),
                    postgresql_using='total_amount::numeric(12,2)')
    # daily_payments
    op.alter_column('daily_payments', 'amount', type_=sa.Numeric(12,2),
                    postgresql_using='amount::numeric(12,2)')
    # purchases
    op.alter_column('purchases', 'total_amount', type_=sa.Numeric(12,2),
                    postgresql_using='total_amount::numeric(12,2)')


def downgrade() -> None:
    # Возвращаем Float (не рекомендуется)
    money_cols = [
        ('items', ['booking_price', 'booking_prepayment', 'sale_price', 'sale_prepayment',
                   'sale_payment_amount', 'booking_bonus', 'sale_bonus', 'sale_change']),
        ('sales', ['cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment']),
        ('preorders', ['cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment']),
        ('bookings', ['total_amount']),
        ('daily_payments', ['amount']),
        ('purchases', ['total_amount'])
    ]
    for table, cols in money_cols:
        for col in cols:
            op.alter_column(table, col, type_=sa.Float(),
                            postgresql_using=f'{col}::double precision')
