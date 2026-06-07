from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import Paper
from app.services.ai import _available_pdf_text_tools, _extract_pdf_text_with_command, normalize_pdf_text
from app.services.candidates import infer_tags, make_initial_parse_markdown, paper_stem, workspace_relative_path, workspace_root
from app.services.chunks import upsert_paper_chunks
from app.services.paper_metadata import project_url_from_mapping, translate_abstract_zh
from app.services.text import stable_key


ARXIV_ID_RE = re.compile(r"(?:arxiv[:/_-]?|abs/|pdf/)?(\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(20\d{2}|19\d{2})\b")


def _clean_filename(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
    return cleaned or "paper.pdf"


def _title_from_filename(filename: str) -> str:
    stem = Path(filename or "Uploaded Paper").stem
    title = re.sub(r"[_-]+", " ", stem).strip()
    return title[:240] or "Uploaded Paper"


def _year_from_text(text: str) -> int | None:
    match = YEAR_RE.search(text or "")
    return int(match.group(1)) if match else None


def _arxiv_id_from_text(text: str) -> str:
    match = ARXIV_ID_RE.search(text or "")
    return match.group(1) if match else ""


async def _arxiv_metadata(arxiv_id: str) -> dict[str, Any]:
    if not arxiv_id:
        return {}
    base_id = arxiv_id.split("v", 1)[0]
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get("https://export.arxiv.org/api/query", params={"id_list": base_id})
        response.raise_for_status()
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(response.text)
    entry = root.find("atom:entry", ns)
    if entry is None:
        return {}
    title = " ".join((entry.findtext("atom:title", default="", namespaces=ns) or "").split())
    abstract = " ".join((entry.findtext("atom:summary", default="", namespaces=ns) or "").split())
    url = entry.findtext("atom:id", default=f"https://arxiv.org/abs/{base_id}", namespaces=ns) or f"https://arxiv.org/abs/{base_id}"
    authors = [node.findtext("atom:name", default="", namespaces=ns) or "" for node in entry.findall("atom:author", ns)]
    published = entry.findtext("atom:published", default="", namespaces=ns) or ""
    ids = {"arxiv": base_id}
    return {
        "key": stable_key(title, ids),
        "title": title or f"arXiv {base_id}",
        "authors": [author for author in authors if author],
        "year": _year_from_text(published),
        "venue": "arXiv",
        "source": "arXiv",
        "sources": ["arXiv"],
        "ids": ids,
        "url": url,
        "pdf": f"https://arxiv.org/pdf/{base_id}",
        "abstract": abstract,
    }


def _abstract_from_text(text: str) -> str:
    normalized = normalize_pdf_text(text)
    match = re.search(r"\babstract\b\s*[:\n]?\s*(.+?)(?:\n\s*(?:1\.?\s+)?introduction\b|\n\s*keywords?\b)", normalized, re.IGNORECASE | re.DOTALL)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()[:1800]
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    return " ".join(lines[1:8])[:1200] if len(lines) > 1 else ""


def _title_from_pdf_text(text: str, fallback: str) -> str:
    for line in normalize_pdf_text(text).splitlines()[:20]:
        title = line.strip()
        if 12 <= len(title) <= 220 and not re.match(r"^(abstract|keywords|introduction)\b", title, re.IGNORECASE):
            return title
    return fallback


def _extract_pdf_text(pdf_path: Path) -> str:
    for command_name, tool_kind in _available_pdf_text_tools():
        try:
            return _extract_pdf_text_with_command(pdf_path, command_name, tool_kind, timeout=90)
        except Exception:
            continue
    return ""


async def _download_pdf(url: str, target: Path) -> bool:
    if not url:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=60, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
        response = await client.get(url)
        response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "pdf" not in content_type and not url.lower().split("?", 1)[0].endswith(".pdf"):
        return False
    target.write_bytes(response.content)
    return True


def _paper_from_metadata(db: Session, workspace_id: int | None, metadata: dict[str, Any]) -> Paper:
    key = metadata.get("key") or stable_key(str(metadata.get("title") or ""), metadata.get("ids") or {"url": metadata.get("url", "")})
    paper = db.scalar(select(Paper).where(Paper.workspace_id == workspace_id, Paper.key == key))
    if paper is None:
        paper = Paper(workspace_id=workspace_id, key=key, title=str(metadata.get("title") or "Untitled"))
        db.add(paper)
    paper.title = str(metadata.get("title") or paper.title or "Untitled")
    paper.authors = metadata.get("authors") or []
    paper.year = metadata.get("year")
    paper.venue = str(metadata.get("venue") or "")
    paper.source = str(metadata.get("source") or "manual")
    paper.sources = metadata.get("sources") or [paper.source]
    paper.ids = metadata.get("ids") or {}
    paper.url = str(metadata.get("url") or "")
    paper.pdf = str(metadata.get("pdf") or "")
    paper.abstract = str(metadata.get("abstract") or "")
    paper.abstract_zh = str(metadata.get("abstract_zh") or "")
    paper.project_url = str(metadata.get("project_url") or project_url_from_mapping(metadata))
    paper.pdf_file_path = str(metadata.get("pdf_file_path") or "")
    paper.initial_parse_markdown = str(metadata.get("initial_parse_markdown") or "")
    paper.tags = metadata.get("tags") or infer_tags(paper.title, paper.abstract)
    paper.status = "accepted"
    paper.reading_status = "candidate"
    paper.priority = str(metadata.get("priority") or "B")
    paper.comment = str(metadata.get("comment") or "手动导入，待人工筛选。")
    return paper


async def import_manual_paper(
    db: Session,
    workspace_id: int | None,
    url: str = "",
    filename: str = "",
    pdf_bytes: bytes | None = None,
) -> Paper:
    url = (url or "").strip()
    arxiv_id = _arxiv_id_from_text(" ".join([url, filename]))
    metadata = await _arxiv_metadata(arxiv_id) if arxiv_id else {}
    pdf_text = ""

    if not metadata:
        title = _title_from_filename(filename or url.rsplit("/", 1)[-1] or "Imported Paper")
        metadata = {
            "title": title,
            "authors": [],
            "year": _year_from_text(" ".join([url, filename])),
            "venue": "Uploaded PDF" if pdf_bytes else "Manual Link",
            "source": "manual",
            "sources": ["manual"],
            "ids": {"url": url} if url else {},
            "url": url,
            "pdf": url if url.lower().split("?", 1)[0].endswith(".pdf") else "",
            "abstract": "",
        }

    paper = _paper_from_metadata(db, workspace_id, metadata)
    db.flush()

    pdf_path: Path | None = None
    if pdf_bytes:
        pdf_name = _clean_filename(filename or f"{paper_stem(paper)}.pdf")
        pdf_path = workspace_root(workspace_id) / "papers" / "pdf" / pdf_name
        pdf_path.write_bytes(pdf_bytes)
        paper.pdf_file_path = workspace_relative_path(pdf_path)
    elif paper.pdf:
        pdf_path = workspace_root(workspace_id) / "papers" / "pdf" / f"{paper_stem(paper)}.pdf"
        try:
            if not pdf_path.exists() and await _download_pdf(paper.pdf, pdf_path):
                paper.pdf_file_path = workspace_relative_path(pdf_path)
        except Exception:
            pdf_path = None

    if pdf_path and pdf_path.exists():
        pdf_text = _extract_pdf_text(pdf_path)
        if pdf_text and not metadata.get("key"):
            paper.title = _title_from_pdf_text(pdf_text, paper.title)
            paper.year = paper.year or _year_from_text(pdf_text[:4000])
            paper.abstract = paper.abstract or _abstract_from_text(pdf_text)

    if not paper.abstract_zh and paper.abstract:
        paper.abstract_zh = await translate_abstract_zh(paper.abstract)
    paper.initial_parse_markdown = make_initial_parse_markdown(paper, pdf_text)
    upsert_paper_chunks(db, paper)
    db.commit()
    db.refresh(paper)
    return paper
