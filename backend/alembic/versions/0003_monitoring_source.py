"""mark real and simulated monitoring data sources

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-26

"""
from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "monitoring_sessions",
        sa.Column("simulated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "monitoring_measurements",
        sa.Column("simulated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("monitoring_measurements", "simulated")
    op.drop_column("monitoring_sessions", "simulated")
