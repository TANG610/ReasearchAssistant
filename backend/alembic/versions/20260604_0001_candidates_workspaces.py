"""add workspaces and search candidates

Revision ID: 20260604_0001
Revises:
Create Date: 2026-06-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.db.base import Base


revision = "20260604_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    if "users" not in existing_tables:
        Base.metadata.create_all(bind=bind)
        return
    if "workspaces" not in existing_tables:
        op.create_table(
            "workspaces",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=200), nullable=False, server_default="默认知识库"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    for table in ["users", "papers", "paper_notes", "paper_chunks", "search_runs", "search_results", "jobs", "chat_sessions", "ideas"]:
        existing_columns = {column["name"] for column in sa.inspect(bind).get_columns(table)}
        if "workspace_id" in existing_columns:
            continue
        op.add_column(table, sa.Column("workspace_id", sa.Integer(), nullable=True))
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])

    paper_columns = {column["name"] for column in sa.inspect(bind).get_columns("papers")}
    for column in ["pdf_file_path", "overview_figure_path", "overview_caption", "initial_parse_markdown"]:
        if column in paper_columns:
            continue
        op.add_column("papers", sa.Column(column, sa.Text(), nullable=False, server_default=""))

    if "search_candidates" in existing_tables:
        return
    op.create_table(
        "search_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("paper_id", sa.Integer(), nullable=True),
        sa.Column("key", sa.String(length=240), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("authors", sa.JSON(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("venue", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("ids", sa.JSON(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False, server_default=""),
        sa.Column("pdf", sa.Text(), nullable=False, server_default=""),
        sa.Column("abstract", sa.Text(), nullable=False, server_default=""),
        sa.Column("abstract_zh", sa.Text(), nullable=False, server_default=""),
        sa.Column("project_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("priority", sa.String(length=10), nullable=False, server_default="B"),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("pdf_file_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("overview_figure_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("overview_caption", sa.Text(), nullable=False, server_default=""),
        sa.Column("initial_parse_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("parse_status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("parse_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["run_id"], ["search_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("workspace_id", "run_id", "key", name="uq_candidates_workspace_run_key"),
    )
    for column in ["workspace_id", "run_id", "paper_id", "key", "title", "priority", "parse_status", "status"]:
        op.create_index(f"ix_search_candidates_{column}", "search_candidates", [column])


def downgrade() -> None:
    op.drop_table("search_candidates")
    for column in ["initial_parse_markdown", "overview_caption", "overview_figure_path", "pdf_file_path"]:
        op.drop_column("papers", column)
    for table in ["ideas", "chat_sessions", "jobs", "search_results", "search_runs", "paper_chunks", "paper_notes", "papers", "users"]:
        op.drop_index(f"ix_{table}_workspace_id", table_name=table)
        op.drop_column(table, "workspace_id")
    op.drop_table("workspaces")
