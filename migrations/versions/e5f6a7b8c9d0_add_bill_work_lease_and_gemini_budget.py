"""Add bill_work_lease and gemini_rate_budget_state

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-05 18:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bill_work_lease',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bill_id', sa.Integer(), nullable=False),
        sa.Column('work_kind', sa.String(length=20), nullable=False),
        sa.Column('holder', sa.String(length=120), nullable=False),
        sa.Column('acquired_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['bill_id'], ['bill.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bill_id', 'work_kind', name='uq_bill_work_lease'),
    )
    op.create_index('ix_bill_work_lease_bill_id', 'bill_work_lease', ['bill_id'], unique=False)

    op.create_table(
        'gemini_rate_budget_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('minute_start_epoch', sa.Float(), nullable=False),
        sa.Column('requests_this_minute', sa.Integer(), nullable=False),
        sa.Column('tokens_this_minute', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('gemini_rate_budget_state')
    op.drop_index('ix_bill_work_lease_bill_id', table_name='bill_work_lease')
    op.drop_table('bill_work_lease')
