"""Increase bill status field length from 50 to 500 characters

Revision ID: cb2811eec460
Revises: c8a785650162
Create Date: 2025-07-16 19:16:56.732705

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cb2811eec460'
down_revision = 'c8a785650162'
branch_labels = None
depends_on = None


def upgrade():
    # Increase the status column length from VARCHAR(50) to VARCHAR(500)
    with op.batch_alter_table('bill', schema=None) as batch_op:
        batch_op.alter_column('status',
                              existing_type=sa.VARCHAR(length=50),
                              type_=sa.VARCHAR(length=500))


def downgrade():
    # Revert status column length back to VARCHAR(50)
    with op.batch_alter_table('bill', schema=None) as batch_op:
        batch_op.alter_column('status',
                              existing_type=sa.VARCHAR(length=500),
                              type_=sa.VARCHAR(length=50))
