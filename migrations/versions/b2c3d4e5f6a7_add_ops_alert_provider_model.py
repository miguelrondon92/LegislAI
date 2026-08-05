"""Add provider_model column to ops_alert

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-04 15:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ops_alert', schema=None) as batch_op:
        batch_op.add_column(sa.Column('provider_model', sa.String(length=80), nullable=True))
        batch_op.create_index('ix_ops_alert_provider_model', ['provider_model'], unique=False)


def downgrade():
    with op.batch_alter_table('ops_alert', schema=None) as batch_op:
        batch_op.drop_index('ix_ops_alert_provider_model')
        batch_op.drop_column('provider_model')
