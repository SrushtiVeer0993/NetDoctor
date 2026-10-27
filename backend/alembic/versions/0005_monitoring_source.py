"""label monitoring source and preserve inconclusive connectivity

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26

"""
from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "monitoring_sessions",
        sa.Column("source", sa.String(length=50), nullable=False, server_default="unknown"),
    )
    with op.batch_alter_table("monitoring_measurements") as batch_op:
        batch_op.alter_column(
            "internet_up",
            existing_type=sa.Boolean(),
            nullable=True,
        )


def downgrade():
    op.execute(
        "UPDATE monitoring_measurements SET internet_up = false WHERE internet_up IS NULL"
    )
    with op.batch_alter_table("monitoring_measurements") as batch_op:
        batch_op.alter_column(
            "internet_up",
            existing_type=sa.Boolean(),
            nullable=False,
        )
    op.drop_column("monitoring_sessions", "source")
