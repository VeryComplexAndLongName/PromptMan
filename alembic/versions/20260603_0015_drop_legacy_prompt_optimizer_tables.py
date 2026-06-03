"""drop legacy prompt and optimizer tables

Revision ID: 20260603_0015
Revises: 20260603_0014
Create Date: 2026-06-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260603_0015"
down_revision: str | Sequence[str] | None = "20260603_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists("prompt_tags"):
        op.drop_table("prompt_tags")
    if _table_exists("prompt_versions"):
        op.drop_table("prompt_versions")
    if _table_exists("prompts"):
        op.drop_table("prompts")
    if _table_exists("tags"):
        op.drop_table("tags")
    if _table_exists("configs"):
        op.drop_table("configs")


def downgrade() -> None:
    if not _table_exists("tags"):
        op.create_table(
            "tags",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("name", sa.String(), nullable=False),
        )
        op.create_index("ix_tags_id", "tags", ["id"], unique=False)
        op.create_index("ix_tags_name", "tags", ["name"], unique=True)

    if not _table_exists("prompts"):
        op.create_table(
            "prompts",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.UniqueConstraint("name", "project_id", name="uq_prompt_name_project_id"),
            sa.CheckConstraint("trim(name) <> ''", name="ck_prompts_name_not_blank"),
        )
        op.create_index("ix_prompts_id", "prompts", ["id"], unique=False)
        op.create_index("ix_prompts_name", "prompts", ["name"], unique=False)
        op.create_index("ix_prompts_project_id", "prompts", ["project_id"], unique=False)
        op.create_index("ix_prompts_created_by_id", "prompts", ["created_by_id"], unique=False)
        op.create_index("ix_prompts_updated_by_id", "prompts", ["updated_by_id"], unique=False)

    if not _table_exists("prompt_versions"):
        op.create_table(
            "prompt_versions",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("prompt_id", sa.Integer(), sa.ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("role", sa.String(), nullable=True),
            sa.Column("task", sa.Text(), nullable=False),
            sa.Column("context", sa.Text(), nullable=True),
            sa.Column("constraints", sa.Text(), nullable=True),
            sa.Column("output_format", sa.Text(), nullable=True),
            sa.Column("examples", sa.Text(), nullable=True),
            sa.UniqueConstraint("prompt_id", "version", name="uq_prompt_version"),
            sa.UniqueConstraint(
                "role",
                "task",
                "context",
                "constraints",
                "output_format",
                "examples",
                name="uq_prompt_version_content_fields",
            ),
        )
        op.create_index("ix_prompt_versions_id", "prompt_versions", ["id"], unique=False)
        op.create_index("ix_prompt_versions_created_by_id", "prompt_versions", ["created_by_id"], unique=False)

    if not _table_exists("prompt_tags"):
        op.create_table(
            "prompt_tags",
            sa.Column("prompt_id", sa.Integer(), sa.ForeignKey("prompts.id", ondelete="CASCADE"), primary_key=True, nullable=False),
            sa.Column("tag_id", sa.Integer(), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        )

    if not _table_exists("configs"):
        op.create_table(
            "configs",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("llm_provider", sa.String(), nullable=True),
            sa.Column("llm_model", sa.String(), nullable=True),
            sa.Column("llm_base_url", sa.String(), nullable=True),
            sa.Column("llm_timeout_seconds", sa.Integer(), nullable=True),
            sa.Column("llm_api_token_encrypted", sa.Text(), nullable=True),
            sa.UniqueConstraint("user_id", name="uq_configs_user_id"),
        )
        op.create_index("ix_configs_id", "configs", ["id"], unique=False)
