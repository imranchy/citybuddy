"""add typed place facts

Revision ID: 3d91f0e2c6a4
Revises: 8b4e8d2a7c31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3d91f0e2c6a4"
down_revision: Union[str, Sequence[str], None] = "8b4e8d2a7c31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "place_facts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("fact_type", sa.String(length=60), nullable=False),
        sa.Column("value", sa.String(length=80), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_excerpt", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("extractor_model", sa.String(length=120), nullable=False),
        sa.Column("review_status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("place_id", "fact_type", name="uq_place_facts_place_type"),
    )
    op.create_index("ix_place_facts_place_id", "place_facts", ["place_id"])
    op.create_index("ix_place_facts_fact_type", "place_facts", ["fact_type"])
    op.create_index("ix_place_facts_fingerprint", "place_facts", ["fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_place_facts_fingerprint", table_name="place_facts")
    op.drop_index("ix_place_facts_fact_type", table_name="place_facts")
    op.drop_index("ix_place_facts_place_id", table_name="place_facts")
    op.drop_table("place_facts")
