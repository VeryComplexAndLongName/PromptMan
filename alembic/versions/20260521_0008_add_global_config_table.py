"""
Add global_config table
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '20260521_0008'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'global_config',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('key')
    )

def downgrade() -> None:
    op.drop_table('global_config')
