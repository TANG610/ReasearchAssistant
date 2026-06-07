from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.session import Base


def json_type():
    return JSON().with_variant(JSONB, "postgresql")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Workspace(Base, TimestampMixin):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="默认知识库")


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True)


class Paper(Base, TimestampMixin):
    __tablename__ = "papers"
    __table_args__ = (UniqueConstraint("workspace_id", "key", name="uq_papers_workspace_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(240), index=True)
    title: Mapped[str] = mapped_column(String(1000), index=True)
    authors: Mapped[list[str]] = mapped_column(json_type(), default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    venue: Mapped[str] = mapped_column(String(240), default="")
    source: Mapped[str] = mapped_column(String(120), default="")
    sources: Mapped[list[str]] = mapped_column(json_type(), default=list)
    ids: Mapped[dict] = mapped_column(json_type(), default=dict)
    url: Mapped[str] = mapped_column(Text, default="")
    pdf: Mapped[str] = mapped_column(Text, default="")
    abstract: Mapped[str] = mapped_column(Text, default="")
    abstract_zh: Mapped[str] = mapped_column(Text, default="")
    project_url: Mapped[str] = mapped_column(Text, default="")
    pdf_file_path: Mapped[str] = mapped_column(Text, default="")
    overview_figure_path: Mapped[str] = mapped_column(Text, default="")
    overview_caption: Mapped[str] = mapped_column(Text, default="")
    initial_parse_markdown: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list[str]] = mapped_column(json_type(), default=list)
    status: Mapped[str] = mapped_column(String(40), default="candidate", index=True)
    reading_status: Mapped[str] = mapped_column(String(40), default="candidate", index=True)
    priority: Mapped[str] = mapped_column(String(10), default="B", index=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    note_path: Mapped[str] = mapped_column(Text, default="")
    note_markdown: Mapped[str] = mapped_column(Text, default="")

    notes: Mapped[list["PaperNote"]] = relationship(back_populates="paper", cascade="all, delete-orphan")
    chunks: Mapped[list["PaperChunk"]] = relationship(back_populates="paper", cascade="all, delete-orphan")


class PaperNote(Base, TimestampMixin):
    __tablename__ = "paper_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(80), default="manual")
    content: Mapped[str] = mapped_column(Text, default="")

    paper: Mapped[Paper] = relationship(back_populates="notes")


class PaperChunk(Base, TimestampMixin):
    __tablename__ = "paper_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    chunk_type: Mapped[str] = mapped_column(String(80), default="note")
    content: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list[float] | None] = mapped_column(json_type(), nullable=True)

    paper: Mapped[Paper] = relationship(back_populates="chunks")


class SearchRun(Base, TimestampMixin):
    __tablename__ = "search_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    query: Mapped[str] = mapped_column(String(500), index=True)
    sources: Mapped[list[str]] = mapped_column(json_type(), default=list)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)

    results: Mapped[list["SearchResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    candidates: Mapped[list["SearchCandidate"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class SearchCandidate(Base, TimestampMixin):
    __tablename__ = "search_candidates"
    __table_args__ = (UniqueConstraint("workspace_id", "run_id", "key", name="uq_candidates_workspace_run_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("search_runs.id", ondelete="CASCADE"), index=True)
    paper_id: Mapped[int | None] = mapped_column(ForeignKey("papers.id", ondelete="SET NULL"), nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(240), index=True)
    title: Mapped[str] = mapped_column(String(1000), index=True)
    authors: Mapped[list[str]] = mapped_column(json_type(), default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str] = mapped_column(String(240), default="")
    source: Mapped[str] = mapped_column(String(120), default="")
    sources: Mapped[list[str]] = mapped_column(json_type(), default=list)
    ids: Mapped[dict] = mapped_column(json_type(), default=dict)
    url: Mapped[str] = mapped_column(Text, default="")
    pdf: Mapped[str] = mapped_column(Text, default="")
    abstract: Mapped[str] = mapped_column(Text, default="")
    abstract_zh: Mapped[str] = mapped_column(Text, default="")
    project_url: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list[str]] = mapped_column(json_type(), default=list)
    priority: Mapped[str] = mapped_column(String(10), default="B", index=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    pdf_file_path: Mapped[str] = mapped_column(Text, default="")
    overview_figure_path: Mapped[str] = mapped_column(Text, default="")
    overview_caption: Mapped[str] = mapped_column(Text, default="")
    initial_parse_markdown: Mapped[str] = mapped_column(Text, default="")
    parse_status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    parse_error: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)

    run: Mapped[SearchRun] = relationship(back_populates="candidates")


class SearchResult(Base, TimestampMixin):
    __tablename__ = "search_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("search_runs.id", ondelete="CASCADE"), index=True)
    paper_id: Mapped[int | None] = mapped_column(ForeignKey("papers.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(1000), index=True)
    authors: Mapped[list[str]] = mapped_column(json_type(), default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str] = mapped_column(String(240), default="")
    source: Mapped[str] = mapped_column(String(120), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    pdf: Mapped[str] = mapped_column(Text, default="")
    abstract: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)

    run: Mapped[SearchRun] = relationship(back_populates="results")


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    payload: Mapped[dict] = mapped_column(json_type(), default=dict)
    result: Mapped[dict] = mapped_column(json_type(), default=dict)
    error: Mapped[str] = mapped_column(Text, default="")


class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(240), default="新对话")

    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base, TimestampMixin):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[dict]] = mapped_column(json_type(), default=list)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class Idea(Base, TimestampMixin):
    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="open", index=True)
