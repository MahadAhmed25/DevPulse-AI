"""initial schema

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-08
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=True, unique=True),
        sa.Column("github_id", sa.Integer(), nullable=True, unique=True),
        sa.Column("github_username", sa.String(255), nullable=True),
        sa.Column("github_access_token", sa.String(512), nullable=True),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True, unique=True),
        sa.Column("subscription_tier", sa.String(20), nullable=False, server_default="free"),
        sa.Column("subscription_status", sa.String(20), nullable=False, server_default="inactive"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_github_id", "users", ["github_id"])

    # ------------------------------------------------------------------
    # repositories
    # ------------------------------------------------------------------
    op.create_table(
        "repositories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("github_repo_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("full_name", sa.String(512), nullable=False),
        sa.Column("default_branch", sa.String(255), nullable=False, server_default="main"),
        sa.Column("webhook_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_indexed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("index_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("index_error", sa.Text(), nullable=True),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_repositories_owner_id", "repositories", ["owner_id"])
    op.create_index("ix_repositories_github_repo_id", "repositories", ["github_repo_id"])

    # ------------------------------------------------------------------
    # pull_requests
    # ------------------------------------------------------------------
    op.create_table(
        "pull_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "repository_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("github_pr_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("author_github_login", sa.String(255), nullable=False),
        sa.Column("base_branch", sa.String(255), nullable=False),
        sa.Column("head_branch", sa.String(255), nullable=False),
        sa.Column("diff_s3_key", sa.String(1024), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("files_changed", sa.Integer(), nullable=True),
        sa.Column("lines_added", sa.Integer(), nullable=True),
        sa.Column("lines_removed", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("repository_id", "github_pr_number", name="uq_pr_repo_number"),
    )
    op.create_index("ix_pull_requests_repository_id", "pull_requests", ["repository_id"])

    # ------------------------------------------------------------------
    # reviews
    # ------------------------------------------------------------------
    op.create_table(
        "reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "pull_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pull_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("structured_review", postgresql.JSONB(), nullable=True),
        sa.Column("s3_review_key", sa.String(1024), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("total_comments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bugs_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("suggestions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("security_flags_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("style_issues_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("posted_to_github", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("github_review_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_reviews_pull_request_id", "reviews", ["pull_request_id"])

    # ------------------------------------------------------------------
    # code_chunks  (requires pgvector extension from migration 0001)
    # ------------------------------------------------------------------
    op.create_table(
        "code_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "repository_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_code_chunks_repository_id", "code_chunks", ["repository_id"])


def downgrade() -> None:
    op.drop_table("code_chunks")
    op.drop_table("reviews")
    op.drop_table("pull_requests")
    op.drop_table("repositories")
    op.drop_table("users")
