"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2025-04-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Создание таблиц
    op.create_table('clients',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('full_name', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('phones', sa.String(), nullable=True),
        sa.Column('telegram_username', sa.String(), nullable=True),
        sa.Column('social_network', sa.String(), nullable=True),
        sa.Column('referral_source', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    op.create_table('deleted_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=True),
        sa.Column('text', sa.String(), nullable=True),
        sa.Column('serial', sa.String(), nullable=True),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('reason', sa.String(), nullable=True),
        sa.Column('restored', sa.Boolean(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('preorders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cash', sa.Float(), nullable=True),
        sa.Column('terminal', sa.Float(), nullable=True),
        sa.Column('qr', sa.Float(), nullable=True),
        sa.Column('transfer', sa.Float(), nullable=True),
        sa.Column('invoice', sa.Float(), nullable=True),
        sa.Column('installment', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('processed_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('processed_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('chat_id', 'message_id', name='uq_processed_messages')
    )

    op.create_table('items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('text', sa.String(), nullable=False),
        sa.Column('serial', sa.String(), nullable=True),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('is_booked', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_items_serial_unique', 'items', ['serial'], unique=True, postgresql_where=sa.text('serial IS NOT NULL'))

    op.create_table('purchases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('items_json', sa.Text(), nullable=True),
        sa.Column('total_amount', sa.Float(), nullable=True),
        sa.Column('payment_details', sa.Text(), nullable=True),
        sa.Column('purchase_type', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('sales',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=True),
        sa.Column('count', sa.Integer(), nullable=True),
        sa.Column('cash', sa.Float(), nullable=True),
        sa.Column('terminal', sa.Float(), nullable=True),
        sa.Column('qr', sa.Float(), nullable=True),
        sa.Column('transfer', sa.Float(), nullable=True),
        sa.Column('invoice', sa.Float(), nullable=True),
        sa.Column('installment', sa.Float(), nullable=True),
        sa.Column('is_accessory', sa.Boolean(), nullable=True),
        sa.Column('message_id', sa.BigInteger(), nullable=True),
        sa.Column('sold_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id')
    )

    op.create_table('bookings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=True),
        sa.Column('total_amount', sa.Float(), nullable=True),
        sa.Column('booked_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('daily_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('payment_type', sa.String(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("type IN ('sale', 'preorder')", name='type_check'),
        sa.CheckConstraint("payment_type IN ('cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment')", name='payment_type_check')
    )
    op.create_index('idx_daily_payments_created_at', 'daily_payments', ['created_at'])


def downgrade() -> None:
    op.drop_index('idx_daily_payments_created_at', table_name='daily_payments')
    op.drop_table('daily_payments')
    op.drop_table('bookings')
    op.drop_table('sales')
    op.drop_table('purchases')
    op.drop_index('idx_items_serial_unique', table_name='items')
    op.drop_table('items')
    op.drop_table('processed_messages')
    op.drop_table('preorders')
    op.drop_table('deleted_items')
    op.drop_table('categories')
    op.drop_table('clients')
