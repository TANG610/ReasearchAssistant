import asyncio
import json
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api import routes
from app.core.config import get_settings
from app.db.base import Base
from app.models.entities import Paper, PaperChunk, PaperNote, SearchCandidate, SearchRun, User, Workspace
from app.services.candidates import backfill_paper_overviews, candidate_from_search_item, ingest_candidate, paper_stem
from app.services.manual_import import import_manual_paper


def make_db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_candidate_ingest_creates_paper_and_chunks() -> None:
    with make_db() as db:
        workspace = Workspace(name="test")
        db.add(workspace)
        db.flush()
        run = SearchRun(workspace_id=workspace.id, query="3dgs", sources=["arxiv"], status="completed")
        db.add(run)
        db.flush()
        candidate = candidate_from_search_item(
            run.id,
            workspace.id,
            {
                "key": "arxiv:2601.00001",
                "title": "Text Driven 3DGS Editing",
                "authors": ["Ada"],
                "year": 2026,
                "venue": "arXiv",
                "source": "arXiv",
                "url": "https://arxiv.org/abs/2601.00001",
                "pdf": "https://arxiv.org/pdf/2601.00001",
                "abstract": "A paper about text driven Gaussian Splatting editing.",
                "abstract_zh": "一篇关于文本驱动 Gaussian Splatting 编辑的论文。",
            },
        )
        candidate.initial_parse_markdown = "## 初步解析\n\n方法框架待精读确认。"
        db.add(candidate)
        db.flush()

        paper = ingest_candidate(db, candidate)
        db.commit()

        saved = db.scalar(select(Paper).where(Paper.id == paper.id))
        chunks = list(db.scalars(select(PaperChunk).where(PaperChunk.paper_id == paper.id)).all())

        assert saved is not None
        assert saved.workspace_id == workspace.id
        assert saved.abstract_zh.startswith("一篇关于")
        assert candidate.status == "ingested"
        assert {chunk.chunk_type for chunk in chunks} >= {"metadata", "abstract", "initial_parse"}


def test_candidate_ingest_is_workspace_scoped() -> None:
    with make_db() as db:
        left = Workspace(name="left")
        right = Workspace(name="right")
        db.add_all([left, right])
        db.flush()
        left_run = SearchRun(workspace_id=left.id, query="3dgs", sources=["arxiv"], status="completed")
        right_run = SearchRun(workspace_id=right.id, query="3dgs", sources=["arxiv"], status="completed")
        db.add_all([left_run, right_run])
        db.flush()
        for run, workspace in [(left_run, left), (right_run, right)]:
            db.add(
                SearchCandidate(
                    workspace_id=workspace.id,
                    run_id=run.id,
                    key="arxiv:same",
                    title=f"{workspace.name} Paper",
                    authors=[],
                    sources=["arxiv"],
                    ids={"arxiv": "same"},
                    priority="B",
                    status="pending",
                )
            )
        db.flush()

        for candidate in db.scalars(select(SearchCandidate)).all():
            ingest_candidate(db, candidate)
        db.commit()

        papers = list(db.scalars(select(Paper).order_by(Paper.workspace_id)).all())

        assert len(papers) == 2
        assert {paper.workspace_id for paper in papers} == {left.id, right.id}


def test_manual_pdf_import_creates_initial_paper_and_chunks(tmp_path: Path, monkeypatch) -> None:
    kb = tmp_path / "knowledge_base"
    settings = get_settings()
    monkeypatch.setattr(settings, "knowledge_base_dir", kb)
    with make_db() as db:
        workspace = Workspace(name="test")
        db.add(workspace)
        db.flush()

        paper = asyncio.run(
            import_manual_paper(
                db,
                workspace.id,
                filename="Manual Import 2026.pdf",
                pdf_bytes=b"%PDF-1.4\nfake pdf",
            )
        )
        chunks = list(db.scalars(select(PaperChunk).where(PaperChunk.paper_id == paper.id)).all())

        assert paper.title == "Manual Import 2026"
        assert paper.year == 2026
        assert paper.pdf_file_path.endswith(".pdf")
        assert paper.note_markdown == ""
        assert {chunk.chunk_type for chunk in chunks} >= {"metadata", "initial_parse"}


def test_delete_paper_removes_metadata_notes_and_chunks() -> None:
    with make_db() as db:
        workspace = Workspace(name="test")
        user = User(username="admin", password_hash="hash", workspace_id=1)
        db.add_all([workspace, user])
        db.flush()
        user.workspace_id = workspace.id
        paper = Paper(workspace_id=workspace.id, key="title:delete", title="Delete Me")
        db.add(paper)
        db.flush()
        db.add(PaperNote(workspace_id=workspace.id, paper_id=paper.id, source="manual", content="note"))
        db.add(PaperChunk(workspace_id=workspace.id, paper_id=paper.id, chunk_type="metadata", content="chunk"))
        db.commit()
        paper_id = paper.id

        result = routes.delete_paper(paper_id, db, user)

        assert result == {"deleted": True, "id": paper_id}
        assert db.get(Paper, paper_id) is None
        assert list(db.scalars(select(PaperNote).where(PaperNote.paper_id == paper_id)).all()) == []
        assert list(db.scalars(select(PaperChunk).where(PaperChunk.paper_id == paper_id)).all()) == []


def test_backfill_paper_overviews_uses_existing_mineru_cache(tmp_path: Path, monkeypatch) -> None:
    kb = tmp_path / "knowledge_base"
    settings = get_settings()
    monkeypatch.setattr(settings, "knowledge_base_dir", kb)
    with make_db() as db:
        workspace = Workspace(name="test")
        db.add(workspace)
        db.flush()
        paper = Paper(
            workspace_id=workspace.id,
            key="arxiv:2601.00001",
            title="Overview Paper",
            abstract="A method overview paper.",
            pdf="https://example.com/paper.pdf",
        )
        db.add(paper)
        db.flush()
        cache_dir = kb / "workspaces" / str(workspace.id) / "cache" / "mineru" / paper_stem(paper)
        image_dir = cache_dir / "images"
        image_dir.mkdir(parents=True)
        (image_dir / "fig1.jpg").write_bytes(b"fake image")
        (cache_dir / "paper_content_list.json").write_text(
            json.dumps(
                [
                    {
                        "type": "image",
                        "img_path": "images/fig1.jpg",
                        "image_caption": "Figure 1: Method overview and framework.",
                    }
                ]
            ),
            encoding="utf-8",
        )

        result = asyncio.run(backfill_paper_overviews(db, workspace_id=workspace.id))
        db.refresh(paper)

        assert result["updated"] == 1
        assert paper.overview_figure_path.endswith("-overview.jpg")
        assert paper.overview_caption == "Figure 1: Method overview and framework."
        assert (kb / paper.overview_figure_path).exists()


def test_backfill_paper_overviews_prefers_objectmorpher_pipeline_over_teaser(tmp_path: Path, monkeypatch) -> None:
    kb = tmp_path / "knowledge_base"
    settings = get_settings()
    monkeypatch.setattr(settings, "knowledge_base_dir", kb)
    with make_db() as db:
        workspace = Workspace(name="test")
        db.add(workspace)
        db.flush()
        paper = Paper(
            workspace_id=workspace.id,
            key="arxiv:2603.28152v1",
            title="ObjectMorpher: 3D-Aware Image Editing via Deformable 3DGS Models",
            abstract="ObjectMorpher overview test.",
            pdf="https://example.com/objectmorpher.pdf",
        )
        db.add(paper)
        db.flush()
        cache_dir = kb / "workspaces" / str(workspace.id) / "cache" / "mineru" / paper_stem(paper)
        image_dir = cache_dir / "images"
        image_dir.mkdir(parents=True)
        (image_dir / "fig1.jpg").write_bytes(b"teaser image")
        (image_dir / "fig2.jpg").write_bytes(b"overview image")
        (cache_dir / "paper_content_list.json").write_text(
            json.dumps(
                [
                    {
                        "type": "image",
                        "img_path": "images/fig1.jpg",
                        "image_caption": "Figure 1. Unlike text-based methods that fail to localize subjects, ObjectMorpher uses direct 3D manipulation.",
                    },
                    {"type": "text", "text": "Abstract"},
                    {
                        "type": "text",
                        "text": "Image editing is important. Recent methods remain a major challenge as Fig. 1 shows.",
                    },
                    {
                        "type": "image",
                        "img_path": "images/fig2.jpg",
                        "image_caption": "Figure 2. Overview of our image editing pipeline.",
                    },
                ]
            ),
            encoding="utf-8",
        )

        result = asyncio.run(backfill_paper_overviews(db, workspace_id=workspace.id, force=True))
        db.refresh(paper)

        assert result["updated"] == 1
        assert paper.overview_caption == "Figure 2. Overview of our image editing pipeline."
        assert (kb / paper.overview_figure_path).read_bytes() == b"overview image"


def test_backfill_paper_overviews_skips_low_confidence_figures(tmp_path: Path, monkeypatch) -> None:
    kb = tmp_path / "knowledge_base"
    settings = get_settings()
    monkeypatch.setattr(settings, "knowledge_base_dir", kb)
    with make_db() as db:
        workspace = Workspace(name="test")
        db.add(workspace)
        db.flush()
        paper = Paper(workspace_id=workspace.id, key="arxiv:low", title="Low Confidence Paper", pdf="https://example.com/low.pdf")
        db.add(paper)
        db.flush()
        cache_dir = kb / "workspaces" / str(workspace.id) / "cache" / "mineru" / paper_stem(paper)
        image_dir = cache_dir / "images"
        image_dir.mkdir(parents=True)
        (image_dir / "fig1.jpg").write_bytes(b"low confidence")
        (cache_dir / "paper_content_list.json").write_text(
            json.dumps(
                [
                    {
                        "type": "image",
                        "img_path": "images/fig1.jpg",
                        "image_caption": "Figure 1. Proposed editing examples.",
                    }
                ]
            ),
            encoding="utf-8",
        )

        result = asyncio.run(backfill_paper_overviews(db, workspace_id=workspace.id, force=True))
        db.refresh(paper)

        assert result["updated"] == 0
        assert result["low_confidence"] == 1
        assert paper.overview_figure_path == ""
        assert paper.overview_caption == ""
