"""initial schema: users, diagnostic_runs

Revision ID: 0001
Revises:
Create Date: 2026-09-19

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "diagnostic_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("health_score", sa.Integer, nullable=False),
        sa.Column("gateway_reachable", sa.Boolean, nullable=False),
        sa.Column("internet_reachable", sa.Boolean, nullable=False),
        sa.Column("latency_avg_ms", sa.Float, nullable=True),
        sa.Column("packet_loss_pct", sa.Float, nullable=True),
        sa.Column("dns_response_ms", sa.Float, nullable=True),
        sa.Column("top_finding", sa.String(1000), nullable=True),
        sa.Column("result_json", sa.JSON, nullable=False),
    )


def downgrade():
    op.drop_table("diagnostic_runs")
    op.drop_table("users")
