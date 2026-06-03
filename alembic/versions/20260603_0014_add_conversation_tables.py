"""add conversation tables for thread/message/import workflows

Revision ID: 20260603_0014
Revises: 6543f3d58168
Create Date: 2026-06-03 18:30:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260603_0014"
down_revision = "6543f3d58168"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_threads",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_conversation_threads_id", "conversation_threads", ["id"])
    op.create_index("ix_conversation_threads_project_id", "conversation_threads", ["project_id"])
    op.create_index("ix_conversation_threads_title", "conversation_threads", ["title"])

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("seq_no", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["thread_id"], ["conversation_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("thread_id", "seq_no", name="uq_conversation_message_thread_seq"),
    )
    op.create_index("ix_conversation_messages_id", "conversation_messages", ["id"])
    op.create_index("ix_conversation_messages_thread_id", "conversation_messages", ["thread_id"])
    op.create_index("ix_conversation_messages_role", "conversation_messages", ["role"])

    op.create_table(
        "conversation_imports",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("import_format", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("raw_payload", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["thread_id"], ["conversation_threads.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_conversation_imports_id", "conversation_imports", ["id"])
    op.create_index("ix_conversation_imports_thread_id", "conversation_imports", ["thread_id"])
    op.create_index("ix_conversation_imports_import_format", "conversation_imports", ["import_format"])
    op.create_index("ix_conversation_imports_status", "conversation_imports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_conversation_imports_status", table_name="conversation_imports")
    op.drop_index("ix_conversation_imports_import_format", table_name="conversation_imports")
    op.drop_index("ix_conversation_imports_thread_id", table_name="conversation_imports")
    op.drop_index("ix_conversation_imports_id", table_name="conversation_imports")
    op.drop_table("conversation_imports")

    op.drop_index("ix_conversation_messages_role", table_name="conversation_messages")
    op.drop_index("ix_conversation_messages_thread_id", table_name="conversation_messages")
    op.drop_index("ix_conversation_messages_id", table_name="conversation_messages")
    op.drop_table("conversation_messages")

    op.drop_index("ix_conversation_threads_title", table_name="conversation_threads")
    op.drop_index("ix_conversation_threads_project_id", table_name="conversation_threads")
    op.drop_index("ix_conversation_threads_id", table_name="conversation_threads")
    op.drop_table("conversation_threads")
