"""phase 3-9 tables: devices, speed_tests, traceroute, monitoring, alerts, reports, settings

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-20

"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "network_devices",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.Column("mac", sa.String(17), nullable=True),
        sa.Column("hostname", sa.String(255), nullable=True),
        sa.Column("vendor", sa.String(255), nullable=True),
        sa.Column("response_ms", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="online"),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "speed_tests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("download_mbps", sa.Float, nullable=True),
        sa.Column("upload_mbps", sa.Float, nullable=True),
        sa.Column("latency_ms", sa.Float, nullable=True),
        sa.Column("jitter_ms", sa.Float, nullable=True),
        sa.Column("methodology", sa.String(500), nullable=False),
        sa.Column("simulated", sa.Boolean, nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "traceroute_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("target", sa.String(255), nullable=False),
        sa.Column("supported", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "traceroute_hops",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("traceroute_runs.id"), nullable=False, index=True),
        sa.Column("hop_number", sa.Integer, nullable=False),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("hostname", sa.String(255), nullable=True),
        sa.Column("latency_ms", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="no_response"),
    )

    op.create_table(
        "monitoring_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("interval_seconds", sa.Integer, nullable=False, server_default="5"),
        sa.Column("target", sa.String(255), nullable=False, server_default="8.8.8.8"),
    )
    op.create_table(
        "monitoring_measurements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("monitoring_sessions.id"), nullable=False, index=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("latency_ms", sa.Float, nullable=True),
        sa.Column("packet_loss_pct", sa.Float, nullable=True),
        sa.Column("dns_ms", sa.Float, nullable=True),
        sa.Column("internet_up", sa.Boolean, nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("metric", sa.String(30), nullable=False),
        sa.Column("operator", sa.String(5), nullable=False, server_default=">"),
        sa.Column("threshold", sa.Float, nullable=True),
        sa.Column("consecutive_required", sa.Integer, nullable=False, server_default="3"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "alert_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("rule_id", sa.Integer, sa.ForeignKey("alert_rules.id"), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("metric", sa.String(30), nullable=False),
        sa.Column("current_value", sa.Float, nullable=True),
        sa.Column("baseline_value", sa.Float, nullable=True),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("acknowledged", sa.Boolean, nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("diagnostic_run_id", sa.Integer, sa.ForeignKey("diagnostic_runs.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
    )

    op.create_table(
        "user_settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, unique=True, index=True),
        sa.Column("monitoring_interval_seconds", sa.Integer, nullable=False, server_default="5"),
        sa.Column("default_ping_target", sa.String(255), nullable=False, server_default="8.8.8.8"),
        sa.Column("default_dns_domain", sa.String(255), nullable=False, server_default="google.com"),
        sa.Column("demo_mode", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("latency_alert_ms", sa.Float, nullable=False, server_default="150"),
        sa.Column("packet_loss_alert_pct", sa.Float, nullable=False, server_default="5"),
        sa.Column("alert_consecutive_checks", sa.Integer, nullable=False, server_default="3"),
    )


def downgrade():
    op.drop_table("user_settings")
    op.drop_table("reports")
    op.drop_table("alert_events")
    op.drop_table("alert_rules")
    op.drop_table("monitoring_measurements")
    op.drop_table("monitoring_sessions")
    op.drop_table("traceroute_hops")
    op.drop_table("traceroute_runs")
    op.drop_table("speed_tests")
    op.drop_table("network_devices")
