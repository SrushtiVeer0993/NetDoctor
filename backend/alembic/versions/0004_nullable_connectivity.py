"""preserve inconclusive connectivity measurements

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26

"""
from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("diagnostic_runs") as batch_op:
        batch_op.alter_column(
            "gateway_reachable",
            existing_type=sa.Boolean(),
            nullable=True,
        )
        batch_op.alter_column(
            "internet_reachable",
            existing_type=sa.Boolean(),
            nullable=True,
        )


def downgrade():
    op.execute(
        "UPDATE diagnostic_runs SET gateway_reachable = false "
        "WHERE gateway_reachable IS NULL"
    )
    op.execute(
        "UPDATE diagnostic_runs SET internet_reachable = false "
        "WHERE internet_reachable IS NULL"
    )
    with op.batch_alter_table("diagnostic_runs") as batch_op:
        batch_op.alter_column(
            "gateway_reachable",
            existing_type=sa.Boolean(),
            nullable=False,
        )
        batch_op.alter_column(
            "internet_reachable",
            existing_type=sa.Boolean(),
            nullable=False,
        )
