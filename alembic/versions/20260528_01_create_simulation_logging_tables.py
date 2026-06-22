"""create simulation logging tables

Revision ID: 20260528_01
Revises: 
Create Date: 2026-05-28 22:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260528_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("comparison_group_id", sa.String(length=64), nullable=True),
        sa.Column("engine", sa.String(length=32), nullable=False),
        sa.Column("controller_mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("intersection_type", sa.String(length=32), nullable=False),
        sa.Column("sumo_cfg", sa.String(length=255), nullable=True),
        sa.Column("tl_id", sa.String(length=64), nullable=True),
        sa.Column("resolved_tl_id", sa.String(length=64), nullable=True),
        sa.Column("use_gui", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("custom_fourway_logic", sa.Boolean(), nullable=True),
        sa.Column("duration_steps", sa.Integer(), nullable=False),
        sa.Column("min_green", sa.Integer(), nullable=False),
        sa.Column("max_green", sa.Integer(), nullable=False),
        sa.Column("yellow", sa.Integer(), nullable=False),
        sa.Column("all_red", sa.Integer(), nullable=False),
        sa.Column("weighted_by_dir", sa.JSON(), nullable=True),
        sa.Column("phase_plan", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("avg_wait_s", sa.Float(), nullable=True),
        sa.Column("avg_red_s", sa.Float(), nullable=True),
        sa.Column("max_red_s", sa.Float(), nullable=True),
        sa.Column("max_queue", sa.Float(), nullable=True),
        sa.Column("avg_queue", sa.Float(), nullable=True),
        sa.Column("throughput_per_min", sa.Float(), nullable=True),
        sa.Column("density_index", sa.Float(), nullable=True),
        sa.Column("phase_fairness_gap", sa.Float(), nullable=True),
        sa.Column("total_served", sa.Float(), nullable=True),
    )
    op.create_index("ix_simulation_runs_comparison_group_id", "simulation_runs", ["comparison_group_id"])

    op.create_table(
        "phase_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("simulation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("phase_name", sa.String(length=64), nullable=False),
        sa.Column("phase_index", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("assigned_duration", sa.Integer(), nullable=True),
        sa.Column("actual_duration", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("directions", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_phase_events_run_id", "phase_events", ["run_id"])

    op.create_table(
        "simulation_step_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("simulation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("phase_name", sa.String(length=64), nullable=False),
        sa.Column("phase_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("green_time", sa.Integer(), nullable=False),
        sa.Column("queue_total", sa.Float(), nullable=False),
        sa.Column("avg_wait_s", sa.Float(), nullable=False),
        sa.Column("phase_queue", sa.Float(), nullable=True),
        sa.Column("phase_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_simulation_step_metrics_run_id", "simulation_step_metrics", ["run_id"])

    op.create_table(
        "direction_step_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("simulation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("is_green", sa.Boolean(), nullable=False),
        sa.Column("queue_count", sa.Float(), nullable=False),
        sa.Column("red_age", sa.Integer(), nullable=False),
        sa.Column("red_streak", sa.Integer(), nullable=False),
        sa.Column("pressure", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_direction_step_metrics_run_id", "direction_step_metrics", ["run_id"])

    op.create_table(
        "direction_run_stats",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("simulation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("green_count", sa.Integer(), nullable=False),
        sa.Column("total_green_s", sa.Float(), nullable=False),
        sa.Column("avg_green_s", sa.Float(), nullable=False),
        sa.Column("max_green_s", sa.Float(), nullable=False),
        sa.Column("total_red_s", sa.Float(), nullable=False),
        sa.Column("avg_red_s", sa.Float(), nullable=False),
        sa.Column("max_red_s", sa.Float(), nullable=False),
    )
    op.create_index("ix_direction_run_stats_run_id", "direction_run_stats", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_direction_run_stats_run_id", table_name="direction_run_stats")
    op.drop_table("direction_run_stats")
    op.drop_index("ix_direction_step_metrics_run_id", table_name="direction_step_metrics")
    op.drop_table("direction_step_metrics")
    op.drop_index("ix_simulation_step_metrics_run_id", table_name="simulation_step_metrics")
    op.drop_table("simulation_step_metrics")
    op.drop_index("ix_phase_events_run_id", table_name="phase_events")
    op.drop_table("phase_events")
    op.drop_index("ix_simulation_runs_comparison_group_id", table_name="simulation_runs")
    op.drop_table("simulation_runs")
