"""add prompt chain versioning tables

Revision ID: 20260603_0016
Revises: 20260603_0015
Create Date: 2026-06-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260603_0016"
down_revision: str | Sequence[str] | None = "20260603_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("prompt_chains"):
        op.create_table(
            "prompt_chains",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.UniqueConstraint("project_id", "name", name="uq_prompt_chains_project_name"),
            sa.CheckConstraint("trim(name) <> ''", name="ck_prompt_chains_name_not_blank"),
        )
        op.create_index("ix_prompt_chains_id", "prompt_chains", ["id"], unique=False)
        op.create_index("ix_prompt_chains_project_id", "prompt_chains", ["project_id"], unique=False)
        op.create_index("ix_prompt_chains_name", "prompt_chains", ["name"], unique=False)
        op.create_index("ix_prompt_chains_created_by_id", "prompt_chains", ["created_by_id"], unique=False)
        op.create_index("ix_prompt_chains_updated_by_id", "prompt_chains", ["updated_by_id"], unique=False)

    if not _table_exists("prompt_chain_versions"):
        op.create_table(
            "prompt_chain_versions",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("chain_id", sa.Integer(), sa.ForeignKey("prompt_chains.id", ondelete="CASCADE"), nullable=False),
            sa.Column("version_no", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.UniqueConstraint("chain_id", "version_no", name="uq_prompt_chain_versions_chain_version"),
        )
        op.create_index("ix_prompt_chain_versions_id", "prompt_chain_versions", ["id"], unique=False)
        op.create_index("ix_prompt_chain_versions_chain_id", "prompt_chain_versions", ["chain_id"], unique=False)
        op.create_index("ix_prompt_chain_versions_created_by_id", "prompt_chain_versions", ["created_by_id"], unique=False)


def downgrade() -> None:
    if _table_exists("prompt_chain_versions"):
        op.drop_table("prompt_chain_versions")
    if _table_exists("prompt_chains"):
        op.drop_table("prompt_chains")
