"""add place evidence vectors

Revision ID: a17c9d24e5f1
Revises: e924f6ecb091
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision: str = "a17c9d24e5f1"
down_revision: Union[str, Sequence[str], None] = "e924f6ecb091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "place_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=500), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("attribution", sa.Text(), nullable=True),
        sa.Column("license", sa.String(length=100), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("place_id", "source_type", "source_id", name="uq_place_evidence_source"),
    )
    op.create_index("ix_place_evidence_place_id", "place_evidence", ["place_id"])
    op.create_index("ix_place_evidence_fingerprint", "place_evidence", ["fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_place_evidence_fingerprint", table_name="place_evidence")
    op.drop_index("ix_place_evidence_place_id", table_name="place_evidence")
    op.drop_table("place_evidence")
