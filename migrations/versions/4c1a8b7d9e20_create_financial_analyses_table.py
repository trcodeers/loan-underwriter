"""create financial analyses table

Revision ID: 4c1a8b7d9e20
Revises: df0efbfb1829
Create Date: 2026-11-12 15:46:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4c1a8b7d9e20"
down_revision: Union[str, Sequence[str], None] = "df0efbfb1829"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "financial_analyses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("source_document_ids", sa.JSON(), nullable=False),
        sa.Column("calculation_inputs", sa.JSON(), nullable=False),
        sa.Column("calculation_results", sa.JSON(), nullable=False),
        sa.Column("calculation_version", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["loan_applications.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_financial_analyses_application_created_at",
        "financial_analyses",
        ["application_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_financial_analyses_application_created_at",
        table_name="financial_analyses",
    )
    op.drop_table("financial_analyses")
