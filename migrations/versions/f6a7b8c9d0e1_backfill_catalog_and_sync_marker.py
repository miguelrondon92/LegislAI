"""Add backfill catalog cursor and shared sync marker on bill

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-05 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    bill_cols = {c["name"] for c in insp.get_columns("bill")}
    if "synced_congress_update_date" not in bill_cols:
        op.add_column(
            "bill",
            sa.Column("synced_congress_update_date", sa.String(length=40), nullable=True),
        )
    if "backfill_last_visited_at" not in bill_cols:
        op.add_column(
            "bill",
            sa.Column("backfill_last_visited_at", sa.DateTime(), nullable=True),
        )
    if "backfill_catalog_state" not in insp.get_table_names():
        op.create_table(
            "backfill_catalog_state",
            sa.Column("congress", sa.Integer(), nullable=False),
            sa.Column("sort_key", sa.String(length=64), nullable=False),
            sa.Column("next_index", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("congress"),
        )


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if "backfill_catalog_state" in insp.get_table_names():
        op.drop_table("backfill_catalog_state")
    bill_cols = {c["name"] for c in insp.get_columns("bill")}
    if "backfill_last_visited_at" in bill_cols:
        op.drop_column("bill", "backfill_last_visited_at")
    if "synced_congress_update_date" in bill_cols:
        op.drop_column("bill", "synced_congress_update_date")
