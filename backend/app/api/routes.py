from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from jwt import PyJWTError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.entities import ChatMessage, ChatSession, Idea, Job, Paper, PaperChunk, PaperNote, SearchCandidate, SearchResult, SearchRun, User, Workspace
from app.schemas.api import (
    ChatRequest,
    ChatResponse,
    DeepReadRequest,
    JobResponse,
    KnowledgeBaseImportRequest,
    LoginRequest,
    MarkdownExportRequest,
    PaperDetail,
    PaperListItem,
    PaperOverviewBackfillRequest,
    PaperSearchRequest,
    PaperUpdate,
    SearchCandidateItem,
    TokenResponse,
)
from app.services.ai import answer_with_rag, make_deep_read_note
from app.services.chunks import upsert_paper_chunks
from app.services.candidates import backfill_paper_overviews, candidate_from_search_item, ingest_candidate, parse_candidate_assets, workspace_root
from app.services.jobs import complete_job, create_job, fail_job
from app.services.knowledge_base import export_markdown, import_knowledge_base
from app.services.manual_import import import_manual_paper
from app.services.paper_metadata import translate_abstract_zh_sync
from app.services.search import search_papers

router = APIRouter()


def ensure_default_user(db: Session) -> User:
    settings = get_settings()
    user = db.scalar(select(User).where(User.username == settings.app_username))
    if user and user.workspace_id:
        assign_legacy_rows_to_workspace(db, user.workspace_id)
        return user
    workspace = Workspace(name=f"{settings.app_username} 的知识库")
    db.add(workspace)
    db.flush()
    if user:
        user.workspace_id = workspace.id
        db.commit()
        db.refresh(user)
        assign_legacy_rows_to_workspace(db, user.workspace_id)
        return user
    user = User(username=settings.app_username, password_hash=hash_password(settings.app_password))
    user.workspace_id = workspace.id
    db.add(user)
    db.commit()
    db.refresh(user)
    assign_legacy_rows_to_workspace(db, user.workspace_id)
    return user


def assign_legacy_rows_to_workspace(db: Session, target_workspace_id: int | None) -> None:
    if not target_workspace_id:
        return
    for model in [Paper, PaperNote, PaperChunk, SearchResult, SearchRun, SearchCandidate, Job, ChatSession, Idea]:
        db.query(model).filter(model.workspace_id.is_(None)).update({"workspace_id": target_workspace_id}, synchronize_session=False)
    db.commit()


def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    username = payload.get("sub")
    user = db.scalar(select(User).where(User.username == username))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.workspace_id:
        workspace = Workspace(name=f"{user.username} 的知识库")
        db.add(workspace)
        db.flush()
        user.workspace_id = workspace.id
        db.commit()
        db.refresh(user)
        assign_legacy_rows_to_workspace(db, user.workspace_id)
    return user


def workspace_id(user: User | None) -> int | None:
    return user.workspace_id if user else None


def get_owned_paper(db: Session, paper_id: int, user: User | None) -> Paper:
    paper = db.get(Paper, paper_id)
    if not paper or (user and paper.workspace_id != user.workspace_id):
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


def get_owned_candidate(db: Session, candidate_id: int, user: User | None) -> SearchCandidate:
    candidate = db.get(SearchCandidate, candidate_id)
    if not candidate or (user and candidate.workspace_id != user.workspace_id):
        raise HTTPException(status_code=404, detail="Search candidate not found")
    return candidate


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = ensure_default_user(db)
    if payload.username != user.username or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    return TokenResponse(access_token=create_access_token(user.username))


@router.get("/papers", response_model=list[PaperListItem])
def list_papers(
    query: str = "",
    tag: str = "",
    priority: str = "",
    reading_status: str = "",
    year: int | None = None,
    source: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[Paper]:
    stmt = select(Paper).where(Paper.workspace_id == workspace_id(user))
    if query:
        like = f"%{query}%"
        stmt = stmt.where(or_(Paper.title.ilike(like), Paper.abstract.ilike(like), Paper.comment.ilike(like)))
    if priority:
        stmt = stmt.where(Paper.priority == priority)
    if reading_status:
        stmt = stmt.where(Paper.reading_status == reading_status)
    if year:
        stmt = stmt.where(Paper.year == year)
    if source:
        stmt = stmt.where(Paper.source.ilike(f"%{source}%"))
    papers = list(db.scalars(stmt.order_by(Paper.priority, Paper.year.desc().nullslast(), Paper.title)).all())
    if tag:
        papers = [paper for paper in papers if tag in (paper.tags or [])]
    return papers


@router.get("/papers/{paper_id}", response_model=PaperDetail)
def get_paper(paper_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Paper:
    paper = get_owned_paper(db, paper_id, user)
    if not (paper.abstract_zh or "").strip() and (paper.abstract or "").strip():
        translated = translate_abstract_zh_sync(paper.abstract)
        if translated:
            paper.abstract_zh = translated
            db.commit()
            db.refresh(paper)
    return paper


@router.patch("/papers/{paper_id}", response_model=PaperDetail)
def update_paper(payload: PaperUpdate, paper_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Paper:
    paper = get_owned_paper(db, paper_id, user)
    chunk_fields = {"title", "abstract", "abstract_zh", "initial_parse_markdown", "note_markdown"}
    changed_fields = set(payload.model_dump(exclude_unset=True))
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(paper, field, value)
    if changed_fields & chunk_fields:
        upsert_paper_chunks(db, paper)
    db.commit()
    db.refresh(paper)
    return paper


@router.delete("/papers/{paper_id}")
def delete_paper(paper_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict[str, int | bool]:
    paper = get_owned_paper(db, paper_id, user)
    db.query(SearchCandidate).filter(SearchCandidate.workspace_id == user.workspace_id, SearchCandidate.paper_id == paper.id).update(
        {"paper_id": None},
        synchronize_session=False,
    )
    db.query(PaperChunk).filter(PaperChunk.workspace_id == user.workspace_id, PaperChunk.paper_id == paper.id).delete(synchronize_session=False)
    db.query(PaperNote).filter(PaperNote.workspace_id == user.workspace_id, PaperNote.paper_id == paper.id).delete(synchronize_session=False)
    db.delete(paper)
    db.commit()
    return {"deleted": True, "id": paper_id}


@router.post("/papers/import", response_model=PaperDetail)
async def import_paper(
    url: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Paper:
    pdf_bytes = await file.read() if file else None
    filename = file.filename if file else ""
    if not url.strip() and not pdf_bytes:
        raise HTTPException(status_code=400, detail="请提供论文链接或上传 PDF。")
    if file and file.content_type and "pdf" not in file.content_type.lower() and not (filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="目前只支持上传 PDF 文件。")
    return await import_manual_paper(db, user.workspace_id, url=url, filename=filename or "", pdf_bytes=pdf_bytes)


@router.post("/papers/search", response_model=JobResponse)
async def paper_search(payload: PaperSearchRequest, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Job:
    job = create_job(db, "paper_search", payload.model_dump(), workspace_id=user.workspace_id)
    run = SearchRun(workspace_id=user.workspace_id, query=payload.query, sources=payload.sources, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)
    try:
        found = await search_papers(payload.query, payload.sources, payload.limit)
        created = 0
        for item in found:
            candidate = candidate_from_search_item(run.id, user.workspace_id, item)
            db.add(candidate)
            db.flush()
            await parse_candidate_assets(candidate)
            created += 1
            result = SearchResult(
                workspace_id=user.workspace_id,
                run_id=run.id,
                paper_id=None,
                title=item["title"],
                authors=item.get("authors", []),
                year=item.get("year"),
                venue=item.get("venue", ""),
                source=item.get("source", ""),
                url=item.get("url", ""),
                pdf=item.get("pdf", ""),
                abstract=item.get("abstract", ""),
                status=candidate.status,
            )
            db.add(result)
        run.status = "completed"
        db.commit()
        return complete_job(db, job, {"run_id": run.id, "found": len(found), "candidates": created})
    except Exception as exc:  # pragma: no cover - surfaced in API response
        run.status = "failed"
        db.commit()
        return fail_job(db, job, exc)


@router.post("/papers/backfill-overviews", response_model=JobResponse)
async def backfill_overviews(
    payload: PaperOverviewBackfillRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Job:
    job = create_job(db, "paper_overview_backfill", payload.model_dump(), workspace_id=user.workspace_id)
    try:
        result = await backfill_paper_overviews(
            db,
            workspace_id=user.workspace_id,
            force=payload.force,
            parse_missing=payload.parse_missing,
            high_confidence_only=payload.high_confidence_only,
        )
        return complete_job(db, job, result)
    except Exception as exc:  # pragma: no cover - surfaced in API response
        return fail_job(db, job, exc)


@router.get("/search-runs/{run_id}/candidates", response_model=list[SearchCandidateItem])
def list_search_candidates(run_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[SearchCandidate]:
    run = db.get(SearchRun, run_id)
    if not run or run.workspace_id != user.workspace_id:
        raise HTTPException(status_code=404, detail="Search run not found")
    return list(
        db.scalars(
            select(SearchCandidate)
            .where(SearchCandidate.workspace_id == user.workspace_id, SearchCandidate.run_id == run_id)
            .order_by(SearchCandidate.priority, SearchCandidate.year.desc().nullslast(), SearchCandidate.title)
        ).all()
    )


@router.post("/search-candidates/{candidate_id}/ingest", response_model=PaperDetail)
def ingest_search_candidate(candidate_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Paper:
    candidate = get_owned_candidate(db, candidate_id, user)
    paper = ingest_candidate(db, candidate)
    db.commit()
    db.refresh(paper)
    return paper


@router.post("/search-candidates/{candidate_id}/reject", response_model=SearchCandidateItem)
def reject_search_candidate(candidate_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> SearchCandidate:
    candidate = get_owned_candidate(db, candidate_id, user)
    candidate.status = "rejected"
    db.commit()
    db.refresh(candidate)
    return candidate


@router.post("/search-candidates/{candidate_id}/parse", response_model=SearchCandidateItem)
async def reparse_search_candidate(candidate_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> SearchCandidate:
    candidate = get_owned_candidate(db, candidate_id, user)
    await parse_candidate_assets(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


@router.post("/papers/{paper_id}/accept", response_model=PaperDetail)
def accept_paper(paper_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Paper:
    paper = get_owned_paper(db, paper_id, user)
    paper.status = "accepted"
    if paper.reading_status == "rejected":
        paper.reading_status = "candidate"
    db.commit()
    db.refresh(paper)
    return paper


@router.post("/papers/{paper_id}/reject", response_model=PaperDetail)
def reject_paper(paper_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Paper:
    paper = get_owned_paper(db, paper_id, user)
    paper.status = "rejected"
    paper.reading_status = "skipped"
    db.commit()
    db.refresh(paper)
    return paper


@router.post("/papers/{paper_id}/deep-read", response_model=JobResponse)
async def deep_read(
    paper_id: int,
    payload: DeepReadRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Job:
    paper = get_owned_paper(db, paper_id, user)
    job = create_job(db, "deep_read", {"paper_id": paper_id, **payload.model_dump()}, workspace_id=user.workspace_id)
    try:
        note = await make_deep_read_note(paper)
        paper.note_markdown = note
        db.add(PaperNote(workspace_id=user.workspace_id, paper_id=paper.id, source="deep_read", content=note))
        paper.reading_status = "read"
        upsert_paper_chunks(db, paper)
        db.commit()
        return complete_job(db, job, {"paper_id": paper.id, "note_chars": len(note)})
    except Exception as exc:  # pragma: no cover
        return fail_job(db, job, exc)


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: Session = Depends(get_db), user: User = Depends(current_user)) -> ChatResponse:
    session = db.get(ChatSession, payload.session_id) if payload.session_id else None
    if session and session.workspace_id != user.workspace_id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if session is None:
        session = ChatSession(workspace_id=user.workspace_id, title=payload.message[:80] or "新对话")
        db.add(session)
        db.commit()
        db.refresh(session)
    db.add(ChatMessage(session_id=session.id, role="user", content=payload.message, citations=[]))
    answer, citations = await answer_with_rag(db, payload.message, workspace_id=user.workspace_id)
    db.add(ChatMessage(session_id=session.id, role="assistant", content=answer, citations=citations))
    db.commit()
    return ChatResponse(session_id=session.id, answer=answer, citations=citations)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Job:
    job = db.get(Job, job_id)
    if not job or job.workspace_id != user.workspace_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/import/knowledge-base", response_model=JobResponse)
def import_knowledge_base_endpoint(
    payload: KnowledgeBaseImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Job:
    settings = get_settings()
    requested_dir = payload.knowledge_base_dir or payload.vault_path
    knowledge_base_dir = Path(requested_dir) if requested_dir else settings.knowledge_base_dir
    job = create_job(db, "knowledge_base_import", {"knowledge_base_dir": str(knowledge_base_dir)}, workspace_id=user.workspace_id)
    try:
        result = import_knowledge_base(db, knowledge_base_dir, workspace_id=user.workspace_id)
        return complete_job(db, job, result)
    except Exception as exc:
        return fail_job(db, job, exc)


@router.post("/import/obsidian", response_model=JobResponse)
def import_legacy_obsidian(
    payload: KnowledgeBaseImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Job:
    return import_knowledge_base_endpoint(payload, db, user)


@router.post("/export/markdown", response_model=JobResponse)
def export_knowledge_base_markdown(
    payload: MarkdownExportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Job:
    settings = get_settings()
    export_path = Path(payload.export_path) if payload.export_path else settings.knowledge_base_dir
    job = create_job(db, "markdown_export", {"export_path": str(export_path)}, workspace_id=user.workspace_id)
    try:
        result = export_markdown(db, export_path, workspace_id=user.workspace_id)
        return complete_job(db, job, result)
    except Exception as exc:
        return fail_job(db, job, exc)


def user_from_query_token(token: str, db: Session) -> User:
    try:
        payload = decode_access_token(token)
    except PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    username = payload.get("sub")
    user = db.scalar(select(User).where(User.username == username))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@router.get("/files/{file_path:path}")
def get_file(
    file_path: str,
    token: str = Query(default=""),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> FileResponse:
    if token:
        user = user_from_query_token(token, db)
    else:
        user = current_user(authorization, db)
    root = get_settings().knowledge_base_dir.resolve()
    target = (root / file_path).resolve()
    allowed_root = workspace_root(user.workspace_id).resolve()
    if allowed_root not in target.parents and target != allowed_root:
        raise HTTPException(status_code=403, detail="File is outside current workspace")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target)
