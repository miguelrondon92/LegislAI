"""Add ops_alert table for programmer-facing system alerts

Revision ID: a1b2c3d4e5f6
Revises: cb2811eec460
Create Date: 2026-08-04 14:56:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = 'cb2811eec460'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ops_alert',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('failure_class', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('bill_identifier', sa.String(length=50), nullable=True),
        sa.Column('bill_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('completion_percentage', sa.Float(), nullable=True),
        sa.Column('extra_json', sa.Text(), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('webhook_sent', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['bill_id'], ['bill.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('ops_alert', schema=None) as batch_op:
        batch_op.create_index('ix_ops_alert_failure_class', ['failure_class'], unique=False)
        batch_op.create_index('ix_ops_alert_bill_identifier', ['bill_identifier'], unique=False)
        batch_op.create_index('ix_ops_alert_is_read', ['is_read'], unique=False)
        batch_op.create_index('ix_ops_alert_created_at', ['created_at'], unique=False)


def downgrade():
    with op.batch_alter_table('ops_alert', schema=None) as batch_op:
        batch_op.drop_index('ix_ops_alert_created_at')
        batch_op.drop_index('ix_ops_alert_is_read')
        batch_op.drop_index('ix_ops_alert_bill_identifier')
        batch_op.drop_index('ix_ops_alert_failure_class')
    op.drop_table('ops_alert')
