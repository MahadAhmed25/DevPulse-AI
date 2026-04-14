"""bigint_github_review_id

Revision ID: c6edf5d1e7ce
Revises: 0002
Create Date: 2026-04-14 16:00:34.659630

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6edf5d1e7ce'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('repositories_github_repo_id_key', 'repositories', type_='unique')
    op.drop_index('ix_repositories_github_repo_id', table_name='repositories')
    op.create_index(op.f('ix_repositories_github_repo_id'), 'repositories', ['github_repo_id'], unique=True)
    op.alter_column('users', 'email',
               existing_type=sa.VARCHAR(length=255),
               nullable=False)
    op.drop_constraint('users_email_key', 'users', type_='unique')
    op.drop_constraint('users_github_id_key', 'users', type_='unique')
    op.drop_index('ix_users_email', table_name='users')
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.drop_index('ix_users_github_id', table_name='users')
    op.create_index(op.f('ix_users_github_id'), 'users', ['github_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_github_id'), table_name='users')
    op.create_index('ix_users_github_id', 'users', ['github_id'], unique=False)
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.create_index('ix_users_email', 'users', ['email'], unique=False)
    op.create_unique_constraint('users_github_id_key', 'users', ['github_id'])
    op.create_unique_constraint('users_email_key', 'users', ['email'])
    op.alter_column('users', 'email',
               existing_type=sa.VARCHAR(length=255),
               nullable=True)
    op.drop_index(op.f('ix_repositories_github_repo_id'), table_name='repositories')
    op.create_index('ix_repositories_github_repo_id', 'repositories', ['github_repo_id'], unique=False)
    op.create_unique_constraint('repositories_github_repo_id_key', 'repositories', ['github_repo_id'])
