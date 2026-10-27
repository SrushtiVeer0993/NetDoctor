"""scope discovered devices to the subnet where they were observed

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("network_devices", sa.Column("subnet", sa.String(length=43), nullable=True))
    op.create_index(
        "ix_network_devices_user_subnet_ip",
        "network_devices",
        ["user_id", "subnet", "ip"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_network_devices_user_subnet_ip", table_name="network_devices")
    op.drop_column("network_devices", "subnet")
