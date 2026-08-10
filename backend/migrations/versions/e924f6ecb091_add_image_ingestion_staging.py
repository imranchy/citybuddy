"""add image ingestion staging

Revision ID: e924f6ecb091
Revises: 6f6f6d719e73
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e924f6ecb091"
down_revision: Union[str, Sequence[str], None] = "6f6f6d719e73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staged_place_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ingestion_run_id", sa.Integer(), nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("wikidata_id", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("source_image_id", sa.String(length=500), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("source_page_url", sa.Text(), nullable=False),
        sa.Column("attribution", sa.Text(), nullable=False),
        sa.Column("license", sa.String(length=100), nullable=False),
        sa.Column("license_url", sa.Text(), nullable=True),
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
        sa.Column("promoted_image_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "promotion_status IN ('pending', 'promoted', 'skipped')",
            name="ck_staged_images_promotion_status",
        ),
        sa.CheckConstraint(
            "validation_status IN ('valid', 'review_required', 'invalid')",
            name="ck_staged_images_validation_status",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"], ["ingestion_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["promoted_image_id"], ["place_images.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ingestion_run_id",
            "place_id",
            "source",
            "source_image_id",
            name="uq_staged_images_run_place_source",
        ),
    )
    op.create_index(
        "ix_staged_place_images_fingerprint", "staged_place_images", ["fingerprint"]
    )
    op.create_index(
        "ix_staged_place_images_ingestion_run_id",
        "staged_place_images",
        ["ingestion_run_id"],
    )
    op.create_index(
        "ix_staged_place_images_place_id", "staged_place_images", ["place_id"]
    )

    op.create_table(
        "image_validation_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("staged_image_id", sa.Integer(), nullable=False),
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
            ["staged_image_id"], ["staged_place_images.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_image_validation_issues_staged_image_id",
        "image_validation_issues",
        ["staged_image_id"],
    )

    op.create_table(
        "image_promotion_batches",
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
            name="ck_image_promotion_batches_status",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"], ["ingestion_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_image_promotion_batches_ingestion_run_id",
        "image_promotion_batches",
        ["ingestion_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_promotion_batches_ingestion_run_id",
        table_name="image_promotion_batches",
    )
    op.drop_table("image_promotion_batches")
    op.drop_index(
        "ix_image_validation_issues_staged_image_id",
        table_name="image_validation_issues",
    )
    op.drop_table("image_validation_issues")
    op.drop_index(
        "ix_staged_place_images_place_id", table_name="staged_place_images"
    )
    op.drop_index(
        "ix_staged_place_images_ingestion_run_id", table_name="staged_place_images"
    )
    op.drop_index(
        "ix_staged_place_images_fingerprint", table_name="staged_place_images"
    )
    op.drop_table("staged_place_images")
