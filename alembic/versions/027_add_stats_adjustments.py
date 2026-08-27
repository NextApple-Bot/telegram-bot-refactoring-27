"""Add stats_adjustments for safe dashboard edits

Revision ID: 027
Revises: 026
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if inspector.has_table("stats_adjustments"):
        return

    op.create_table(
        "stats_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("base_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("target_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("delta", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("target_date", "metric", name="uq_stats_adj_date_metric"),
    )
    op.create_index("idx_stats_adjustments_date", "stats_adjustments", ["target_date"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if not inspector.has_table("stats_adjustments"):
        return
    op.drop_index("idx_stats_adjustments_date", table_name="stats_adjustments")
    op.drop_table("stats_adjustments")
