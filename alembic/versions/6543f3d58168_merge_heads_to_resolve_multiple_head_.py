"""Merge heads to resolve multiple head revisions

Revision ID: 6543f3d58168
Revises: 20260521_0008, 20260521_0013
Create Date: 2026-05-21 02:04:29.256288

"""
from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '6543f3d58168'
down_revision = ('20260521_0008', '20260521_0013')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
