"""Add full_text, full_text_fetched_at, content_hash to bill

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-04 17:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('bill', schema=None) as batch_op:
        batch_op.add_column(sa.Column('full_text', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('full_text_fetched_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('content_hash', sa.String(length=64), nullable=True))
        batch_op.create_index('ix_bill_content_hash', ['content_hash'], unique=False)


def downgrade():
    with op.batch_alter_table('bill', schema=None) as batch_op:
        batch_op.drop_index('ix_bill_content_hash')
        batch_op.drop_column('content_hash')
        batch_op.drop_column('full_text_fetched_at')
        batch_op.drop_column('full_text')
