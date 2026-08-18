"""add agent review decisions

Revision ID: f27b9d4d6c10
Revises: e924f6ecb091
Create Date: 2026-08-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f27b9d4d6c10"
down_revision: Union[str, Sequence[str], None] = "a17c9d24e5f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "staged_places",
        sa.Column(
            "candidate_kind",
            sa.String(length=20),
            server_default="new",
            nullable=False,
        ),
    )
    op.add_column(
        "staged_places",
        sa.Column("target_place_id", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_staged_places_candidate_kind",
        "staged_places",
        "candidate_kind IN ('new', 'enrichment')",
    )
    op.create_foreign_key(
        "fk_staged_places_target_place_id_places",
        "staged_places",
        "places",
        ["target_place_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_staged_places_target_place_id",
        "staged_places",
        ["target_place_id"],
    )

    op.create_table(
        "agent_review_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ingestion_run_id", sa.Integer(), nullable=False),
        sa.Column("candidate_type", sa.String(length=20), nullable=False),
        sa.Column("staged_place_id", sa.Integer(), nullable=True),
        sa.Column("staged_image_id", sa.Integer(), nullable=True),
        sa.Column("candidate_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("validation_status", sa.String(length=20), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "concerns",
            postgresql.ARRAY(sa.String(length=120)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("reviewer_model", sa.String(length=120), nullable=False),
        sa.Column("escalated", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "candidate_type IN ('place', 'image')",
            name="ck_agent_review_candidate_type",
        ),
        sa.CheckConstraint(
            "verdict IN ('approve', 'reject')",
            name="ck_agent_review_verdict",
        ),
        sa.CheckConstraint(
            "(candidate_type = 'place' AND staged_place_id IS NOT NULL AND staged_image_id IS NULL) "
            "OR (candidate_type = 'image' AND staged_image_id IS NOT NULL AND staged_place_id IS NULL)",
            name="ck_agent_review_candidate_reference",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"], ["ingestion_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["staged_place_id"], ["staged_places.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["staged_image_id"], ["staged_place_images.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_review_decisions_ingestion_run_id",
        "agent_review_decisions",
        ["ingestion_run_id"],
    )
    op.create_index(
        "ix_agent_review_decisions_staged_place_id",
        "agent_review_decisions",
        ["staged_place_id"],
    )
    op.create_index(
        "ix_agent_review_decisions_staged_image_id",
        "agent_review_decisions",
        ["staged_image_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_review_decisions_staged_image_id",
        table_name="agent_review_decisions",
    )
    op.drop_index(
        "ix_agent_review_decisions_staged_place_id",
        table_name="agent_review_decisions",
    )
    op.drop_index(
        "ix_agent_review_decisions_ingestion_run_id",
        table_name="agent_review_decisions",
    )
    op.drop_table("agent_review_decisions")
    op.drop_index("ix_staged_places_target_place_id", table_name="staged_places")
    op.drop_constraint(
        "fk_staged_places_target_place_id_places",
        "staged_places",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_staged_places_candidate_kind",
        "staged_places",
        type_="check",
    )
    op.drop_column("staged_places", "target_place_id")
    op.drop_column("staged_places", "candidate_kind")
