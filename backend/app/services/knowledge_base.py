from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Paper
from app.services.chunks import upsert_paper_chunks
from app.services.paper_metadata import project_url_from_mapping
from app.services.text import stable_key


NOTES_DIR = Path("papers") / "notes"
REPORTS_DIR = Path("reports")
METADATA_DIR = Path("metadata")


def ensure_knowledge_base_dirs(knowledge_base_dir: Path) -> None:
    for relative in [
        Path("papers") / "pdf",
        NOTES_DIR,
        Path("indexes"),
        REPORTS_DIR,
        Path("assets") / "figures",
        Path("cache") / "pdf_text",
        Path("cache") / "mineru",
        METADATA_DIR,
    ]:
        (knowledge_base_dir / relative).mkdir(parents=True, exist_ok=True)


def _read_markdown(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _strip_frontmatter(markdown: str) -> str:
    if not markdown.startswith("---"):
        return markdown
    parts = markdown.split("---", 2)
    if len(parts) < 3:
        return markdown
    return parts[2].lstrip()


def _frontmatter(markdown: str) -> dict[str, Any]:
    if not markdown.startswith("---"):
        return {}
    parts = markdown.split("---", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


def _library_candidates(knowledge_base_dir: Path) -> list[Path]:
    return [
        knowledge_base_dir / METADATA_DIR / "library.json",
        knowledge_base_dir / "library.json",
        knowledge_base_dir / "data" / "library.json",
    ]


def find_library_path(knowledge_base_dir: Path) -> Path:
    for path in _library_candidates(knowledge_base_dir):
        if path.exists():
            return path
    expected = ", ".join(str(path) for path in _library_candidates(knowledge_base_dir))
    raise FileNotFoundError(f"未找到知识库元数据文件，请提供其中之一：{expected}")


def normalize_note_path(note_path: str, title: str = "", key: str = "") -> str:
    raw = Path(note_path) if note_path else Path()
    name = raw.name
    if not name:
        stem = (key or stable_key(title or "untitled", {})).replace(":", "-")
        name = f"{stem}.md"
    if raw.parts and raw.parts[0].lower() == "papers":
        return (NOTES_DIR / name).as_posix()
    if raw.parts[:2] == ("papers", "notes"):
        return raw.as_posix()
    if len(raw.parts) == 1:
        return (NOTES_DIR / name).as_posix()
    return raw.as_posix()


def _upsert_chunks(db: Session, paper: Paper) -> None:
    upsert_paper_chunks(db, paper)


def import_knowledge_base(db: Session, knowledge_base_dir: Path, workspace_id: int | None = None) -> dict[str, Any]:
    root = knowledge_base_dir.resolve()
    if not root.exists():
        raise FileNotFoundError(f"知识库目录不存在：{root}")
    library_path = find_library_path(root)
    library = json.loads(library_path.read_text(encoding="utf-8"))
    imported = 0
    updated = 0
    notes_found = 0

    for raw in (library.get("papers") or {}).values():
        normalized_note_path = normalize_note_path(raw.get("note_path") or "", raw.get("title") or "", raw.get("key") or "")
        markdown = _read_markdown(root / normalized_note_path) if normalized_note_path else ""
        if markdown:
            notes_found += 1
        fm = _frontmatter(markdown)
        ids = raw.get("ids") or fm.get("ids") or {}
        key = raw.get("key") or stable_key(raw.get("title") or fm.get("title") or "", ids)
        paper = db.scalar(select(Paper).where(Paper.workspace_id == workspace_id, Paper.key == key))
        is_new = paper is None
        if paper is None:
            paper = Paper(workspace_id=workspace_id, key=key, title=raw.get("title") or fm.get("title") or "Untitled")
            db.add(paper)

        paper.title = raw.get("title") or fm.get("title") or paper.title
        paper.authors = raw.get("authors") or fm.get("authors") or []
        paper.year = raw.get("year") or fm.get("year")
        paper.venue = raw.get("venue") or fm.get("venue") or ""
        paper.source = raw.get("source") or fm.get("source") or ""
        paper.sources = raw.get("sources") or ([paper.source] if paper.source else [])
        paper.ids = ids
        paper.url = raw.get("url") or fm.get("url") or ""
        paper.pdf = raw.get("pdf") or fm.get("pdf") or ""
        paper.abstract = raw.get("abstract") or ""
        paper.abstract_zh = raw.get("abstract_zh") or fm.get("abstract_zh") or ""
        paper.project_url = raw.get("project_url") or fm.get("project_url") or project_url_from_mapping(raw, markdown)
        paper.tags = raw.get("tags") or fm.get("tags") or []
        paper.status = raw.get("status") or fm.get("status") or "candidate"
        paper.reading_status = raw.get("reading_status") or fm.get("reading_status") or paper.status
        paper.priority = raw.get("priority") or fm.get("priority") or "B"
        paper.comment = raw.get("comment") or ""
        paper.note_path = normalized_note_path
        paper.note_markdown = _strip_frontmatter(markdown)
        db.flush()
        _upsert_chunks(db, paper)
        imported += 1 if is_new else 0
        updated += 0 if is_new else 1

    db.commit()
    reports = len(list((root / REPORTS_DIR).glob("*.md"))) if (root / REPORTS_DIR).exists() else 0
    return {
        "imported": imported,
        "updated": updated,
        "notes_found": notes_found,
        "reports_found": reports,
        "knowledge_base_dir": str(root),
        "library_path": str(library_path),
    }


def render_paper_markdown(paper: Paper) -> str:
    frontmatter = {
        "title": paper.title,
        "authors": paper.authors,
        "year": paper.year,
        "venue": paper.venue,
        "source": paper.source,
        "ids": paper.ids,
        "url": paper.url,
        "pdf": paper.pdf,
        "abstract_zh": paper.abstract_zh,
        "project_url": paper.project_url,
        "tags": paper.tags,
        "status": paper.status,
        "reading_status": paper.reading_status,
        "priority": paper.priority,
    }
    yaml_text = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    body = paper.note_markdown.strip() or f"# {paper.title}\n\n## 摘要\n\n{paper.abstract}\n"
    return f"---\n{yaml_text}\n---\n\n{body}\n"


def export_markdown(db: Session, knowledge_base_dir: Path, workspace_id: int | None = None) -> dict[str, Any]:
    root = knowledge_base_dir.resolve()
    ensure_knowledge_base_dirs(root)
    papers_dir = root / NOTES_DIR
    count = 0
    for paper in db.scalars(
        select(Paper).where(Paper.workspace_id == workspace_id).order_by(Paper.year.desc().nullslast(), Paper.title)
    ).all():
        note_path = normalize_note_path(paper.note_path, paper.title, paper.key)
        filename = Path(note_path).name
        (papers_dir / filename).write_text(render_paper_markdown(paper), encoding="utf-8")
        paper.note_path = (NOTES_DIR / filename).as_posix()
        count += 1
    db.commit()
    return {"exported": count, "path": str(papers_dir)}
