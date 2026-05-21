"""add cache requests table

Revision ID: 20260521_0013
Revises: 20260518_0012
Create Date: 2026-05-21 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260521_0013"
down_revision: str | None = "20260518_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cache_requests",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("cache_key", sa.String(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("lru", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.CheckConstraint("trim(cache_key) <> ''", name="ck_cache_requests_cache_key_not_blank"),
        sa.UniqueConstraint("cache_key", name="uq_cache_requests_cache_key"),
    )
    op.create_index(op.f("ix_cache_requests_id"), "cache_requests", ["id"], unique=False)
    op.create_index(op.f("ix_cache_requests_cache_key"), "cache_requests", ["cache_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_cache_requests_cache_key"), table_name="cache_requests")
    op.drop_index(op.f("ix_cache_requests_id"), table_name="cache_requests")
    op.drop_table("cache_requests")
