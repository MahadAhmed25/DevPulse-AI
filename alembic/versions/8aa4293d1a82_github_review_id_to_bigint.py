"""github_review_id_to_bigint

Revision ID: 8aa4293d1a82
Revises: c6edf5d1e7ce
Create Date: 2026-04-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '8aa4293d1a82'
down_revision: Union[str, None] = 'c6edf5d1e7ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('reviews', 'github_review_id',
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True)


def downgrade() -> None:
    op.alter_column('reviews', 'github_review_id',
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True)
