"""add ingestion control plane

Revision ID: 6f6f6d719e73
Revises: d036e85608ce
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "6f6f6d719e73"
down_revision: Union[str, Sequence[str], None] = "d036e85608ce"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="running", nullable=False
        ),
        sa.Column(
            "preview_only", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "statistics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_ingestion_runs_status",
        ),
        sa.CheckConstraint(
            "trigger IN ('manual', 'scheduled')",
            name="ck_ingestion_runs_trigger",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_runs_city", "ingestion_runs", ["city"])
    op.create_index("ix_ingestion_runs_source", "ingestion_runs", ["source"])

    op.create_table(
        "staged_places",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ingestion_run_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("address", sa.String(length=300), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("price_level", sa.Integer(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column(
            "dietary_options",
            postgresql.ARRAY(sa.String(length=30)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("opening_hours", sa.Text(), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("operator", sa.String(length=200), nullable=True),
        sa.Column(
            "source_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("validation_status", sa.String(length=20), nullable=False),
        sa.Column(
            "promotion_status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("promoted_place_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "promotion_status IN ('pending', 'promoted', 'skipped')",
            name="ck_staged_places_promotion_status",
        ),
        sa.CheckConstraint(
            "validation_status IN ('valid', 'review_required', 'invalid')",
            name="ck_staged_places_validation_status",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"], ["ingestion_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["promoted_place_id"], ["places.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ingestion_run_id",
            "source",
            "source_id",
            name="uq_staged_places_run_source",
        ),
    )
    op.create_index(
        "ix_staged_places_fingerprint", "staged_places", ["fingerprint"]
    )
    op.create_index(
        "ix_staged_places_ingestion_run_id", "staged_places", ["ingestion_run_id"]
    )

    op.create_table(
        "validation_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("staged_place_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("field", sa.String(length=80), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["staged_place_id"], ["staged_places.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_validation_issues_staged_place_id",
        "validation_issues",
        ["staged_place_id"],
    )

    op.create_table(
        "promotion_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ingestion_run_id", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="running", nullable=False
        ),
        sa.Column(
            "requested_staged_ids", postgresql.ARRAY(sa.Integer()), nullable=False
        ),
        sa.Column("promoted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skipped_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_promotion_batches_status",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"], ["ingestion_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_promotion_batches_ingestion_run_id",
        "promotion_batches",
        ["ingestion_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_promotion_batches_ingestion_run_id", table_name="promotion_batches"
    )
    op.drop_table("promotion_batches")
    op.drop_index(
        "ix_validation_issues_staged_place_id", table_name="validation_issues"
    )
    op.drop_table("validation_issues")
    op.drop_index("ix_staged_places_ingestion_run_id", table_name="staged_places")
    op.drop_index("ix_staged_places_fingerprint", table_name="staged_places")
    op.drop_table("staged_places")
    op.drop_index("ix_ingestion_runs_source", table_name="ingestion_runs")
    op.drop_index("ix_ingestion_runs_city", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
