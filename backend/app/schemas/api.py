from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PaperBase(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str = ""
    source: str = ""
    sources: list[str] = Field(default_factory=list)
    ids: dict[str, Any] = Field(default_factory=dict)
    url: str = ""
    pdf: str = ""
    abstract: str = ""
    abstract_zh: str = ""
    project_url: str = ""
    pdf_file_path: str = ""
    overview_figure_path: str = ""
    overview_caption: str = ""
    initial_parse_markdown: str = ""
    tags: list[str] = Field(default_factory=list)
    status: str = "candidate"
    reading_status: str = "candidate"
    priority: str = "B"
    comment: str = ""
    note_path: str = ""


class PaperListItem(PaperBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    created_at: datetime
    updated_at: datetime


class PaperDetail(PaperListItem):
    note_markdown: str = ""


class PaperUpdate(BaseModel):
    title: str | None = None
    tags: list[str] | None = None
    status: str | None = None
    reading_status: str | None = None
    priority: str | None = None
    comment: str | None = None
    abstract_zh: str | None = None
    project_url: str | None = None
    pdf_file_path: str | None = None
    overview_figure_path: str | None = None
    overview_caption: str | None = None
    initial_parse_markdown: str | None = None
    note_markdown: str | None = None


class PaperSearchRequest(BaseModel):
    query: str = "3d-scene-editing"
    sources: list[str] = Field(default_factory=lambda: ["arxiv"])
    limit: int = 10


class PaperOverviewBackfillRequest(BaseModel):
    force: bool = False
    parse_missing: bool = False
    high_confidence_only: bool = True


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseImportRequest(BaseModel):
    knowledge_base_dir: str | None = None
    vault_path: str | None = None


class MarkdownExportRequest(BaseModel):
    export_path: str | None = None


class ChatRequest(BaseModel):
    message: str
    session_id: int | None = None


class ChatResponse(BaseModel):
    session_id: int
    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)


class DeepReadRequest(BaseModel):
    force: bool = False
    with_figures: bool = False


class SearchRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    query: str
    sources: list[str]
    status: str
    created_at: datetime
    updated_at: datetime


class SearchCandidateItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    paper_id: int | None = None
    key: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str = ""
    source: str = ""
    sources: list[str] = Field(default_factory=list)
    ids: dict[str, Any] = Field(default_factory=dict)
    url: str = ""
    pdf: str = ""
    abstract: str = ""
    abstract_zh: str = ""
    project_url: str = ""
    tags: list[str] = Field(default_factory=list)
    priority: str = "B"
    comment: str = ""
    pdf_file_path: str = ""
    overview_figure_path: str = ""
    overview_caption: str = ""
    initial_parse_markdown: str = ""
    parse_status: str = "pending"
    parse_error: str = ""
    status: str = "pending"
    created_at: datetime
    updated_at: datetime
