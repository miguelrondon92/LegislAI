"""Add provider_model to AIAnalysis, Summary, HiddenProvision

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-04 16:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ai_analysis', schema=None) as batch_op:
        batch_op.add_column(sa.Column('provider_model', sa.String(length=80), nullable=True))
        batch_op.create_index('ix_ai_analysis_provider_model', ['provider_model'], unique=False)

    with op.batch_alter_table('summary', schema=None) as batch_op:
        batch_op.add_column(sa.Column('provider_model', sa.String(length=80), nullable=True))
        batch_op.create_index('ix_summary_provider_model', ['provider_model'], unique=False)

    with op.batch_alter_table('hidden_provision', schema=None) as batch_op:
        batch_op.add_column(sa.Column('provider_model', sa.String(length=80), nullable=True))
        batch_op.create_index('ix_hidden_provision_provider_model', ['provider_model'], unique=False)


def downgrade():
    with op.batch_alter_table('hidden_provision', schema=None) as batch_op:
        batch_op.drop_index('ix_hidden_provision_provider_model')
        batch_op.drop_column('provider_model')

    with op.batch_alter_table('summary', schema=None) as batch_op:
        batch_op.drop_index('ix_summary_provider_model')
        batch_op.drop_column('provider_model')

    with op.batch_alter_table('ai_analysis', schema=None) as batch_op:
        batch_op.drop_index('ix_ai_analysis_provider_model')
        batch_op.drop_column('provider_model')
