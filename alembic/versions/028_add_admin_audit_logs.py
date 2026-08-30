"""Add admin_audit_logs

Revision ID: 028
Revises: 027
Create Date: 2026-08-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if inspector.has_table("admin_audit_logs"):
        return

    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("ix_admin_audit_logs_action", "admin_audit_logs", ["action"])
    op.create_index("ix_admin_audit_logs_created_at", "admin_audit_logs", ["created_at"])
    op.create_index(
        "idx_admin_audit_action_created",
        "admin_audit_logs",
        ["action", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("admin_audit_logs")
