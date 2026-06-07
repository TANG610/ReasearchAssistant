from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import Paper, SearchCandidate
from app.services.ai import _extract_pdf_text_with_mineru_api, normalize_pdf_text
from app.services.chunks import upsert_paper_chunks
from app.services.paper_metadata import project_url_from_mapping
from app.services.text import stable_key


OVERVIEW_TERMS = [
    "architecture",
    "framework",
    "pipeline",
    "overview",
    "method overview",
    "system",
    "workflow",
    "network architecture",
    "model architecture",
    "方法总览",
    "方法框架",
    "整体架构",
    "系统框架",
    "流程图",
]
STRONG_OVERVIEW_TERMS = [
    "method overview",
    "overview",
    "pipeline",
    "architecture",
    "workflow",
    "overall framework",
    "method framework",
    "system framework",
    "proposed framework",
    "方法总览",
    "方法框架",
    "整体架构",
    "系统框架",
    "流程图",
]
LOW_VALUE_TERMS = [
    "qualitative",
    "comparison",
    "ablation",
    "user study",
    "teaser",
    "benchmark",
    "结果",
    "对比",
    "消融",
]
MIN_OVERVIEW_SCORE = 20.0


def slugify(text: str, limit: int = 80) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (slug[:limit].strip("-") or "paper")


def workspace_relative_path(path: Path) -> str:
    root = get_settings().knowledge_base_dir.resolve()
    return path.resolve().relative_to(root).as_posix()


def workspace_root(workspace_id: int | None) -> Path:
    root = get_settings().knowledge_base_dir.resolve()
    suffix = str(workspace_id or 1)
    path = root / "workspaces" / suffix
    for relative in [
        Path("candidates") / "pdf",
        Path("candidates") / "figures",
        Path("papers") / "pdf",
        Path("assets") / "figures",
        Path("cache") / "mineru",
    ]:
        (path / relative).mkdir(parents=True, exist_ok=True)
    return path


def candidate_stem(candidate: SearchCandidate) -> str:
    safe_key = (candidate.key or stable_key(candidate.title, candidate.ids)).replace(":", "-").replace("/", "-")
    return f"{safe_key}-{slugify(candidate.title, 64)}"


def paper_stem(paper: Paper) -> str:
    safe_key = (paper.key or stable_key(paper.title, paper.ids)).replace(":", "-").replace("/", "-")
    return f"{safe_key}-{slugify(paper.title, 64)}"


def infer_tags(title: str, abstract: str = "") -> list[str]:
    text = f"{title} {abstract}".lower()
    tags = ["paper"]
    rules = {
        "scene-editing": ["editing", "editor", "manipulation", "editable"],
        "text-guided": ["text-driven", "text guided", "language-driven", "instruction"],
        "local-editing": ["object removal", "object insertion", "local", "inpainting"],
        "semantic": ["semantic", "segmentation", "instance", "decomposition"],
        "appearance": ["style", "appearance", "texture", "material"],
        "geometry": ["geometry", "deformation", "shape", "dynamic"],
    }
    for tag, terms in rules.items():
        if any(term in text for term in terms):
            tags.append(tag)
    return tags


def infer_priority(data: dict[str, Any]) -> str:
    tags = set(data.get("tags") or infer_tags(str(data.get("title") or ""), str(data.get("abstract") or "")))
    venue = str(data.get("venue") or "").upper()
    text = f"{data.get('title') or ''} {data.get('abstract') or ''}".lower()
    direct_terms = ["editing", "editor", "manipulation", "object removal", "object insertion", "text driven", "language driven"]
    if "scene-editing" in tags and (any(name in venue for name in ["CVPR", "ICCV", "NEURIPS"]) or any(term in text for term in direct_terms)):
        return "A"
    if tags & {"text-guided", "local-editing", "semantic", "appearance", "geometry"}:
        return "B"
    return "C"


def short_comment(data: dict[str, Any]) -> str:
    tags = set(data.get("tags") or [])
    parts = []
    if "scene-editing" in tags:
        parts.append("和 3D 场景编辑直接相关")
    if "text-guided" in tags:
        parts.append("涉及文本或语言驱动")
    if "semantic" in tags:
        parts.append("涉及语义理解或分割")
    if "appearance" in tags:
        parts.append("涉及外观或风格编辑")
    if "geometry" in tags:
        parts.append("涉及几何或形变")
    return "；".join(parts or ["通过关键词搜集发现，需人工筛选"]) + "。"


def make_initial_parse_markdown(candidate: SearchCandidate, pdf_text: str = "") -> str:
    excerpt = normalize_pdf_text(pdf_text)[:5000]
    parts = [
        f"# {candidate.title}",
        "## Metadata",
        f"- Authors: {', '.join(candidate.authors or []) or 'Unknown'}",
        f"- Year: {candidate.year or 'Unknown'}",
        f"- Venue/Source: {candidate.venue or candidate.source or 'Unknown'}",
        f"- Priority: {candidate.priority}",
        f"- URL: {candidate.url or 'N/A'}",
        f"- PDF: {candidate.pdf or 'N/A'}",
        "## Abstract",
        candidate.abstract or "暂无英文摘要。",
        "## 中文摘要",
        candidate.abstract_zh or "暂无中文摘要。",
    ]
    if candidate.overview_caption:
        parts.extend(["## Overview Figure", candidate.overview_caption])
    if excerpt:
        parts.extend(["## PDF Text Excerpt", excerpt])
    return "\n\n".join(parts).strip()


def promote_candidate_file(candidate: SearchCandidate, relative_path: str, target_dir: str) -> str:
    if not relative_path:
        return ""
    root = get_settings().knowledge_base_dir.resolve()
    source = (root / relative_path).resolve()
    if not source.exists() or not source.is_file():
        return relative_path
    destination_dir = workspace_root(candidate.workspace_id) / target_dir
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    return workspace_relative_path(destination)


async def download_candidate_pdf(candidate: SearchCandidate, timeout: int = 30) -> str:
    if candidate.pdf_file_path:
        return candidate.pdf_file_path
    if not candidate.pdf:
        return ""
    target = workspace_root(candidate.workspace_id) / "candidates" / "pdf" / f"{candidate_stem(candidate)}.pdf"
    if not target.exists() or target.stat().st_size <= 0:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(candidate.pdf)
            response.raise_for_status()
        target.write_bytes(response.content)
    return workspace_relative_path(target)


def clean_caption(value: Any) -> str:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text


def describe_exception(exc: Exception) -> str:
    message = str(exc).strip() or repr(exc)
    return f"{exc.__class__.__name__}: {message}"


def score_overview_caption(caption: str) -> float:
    lower = caption.lower()
    if not caption:
        return 0.0
    score = 0.0
    for term in STRONG_OVERVIEW_TERMS:
        if term.lower() in lower:
            score += 20
    if "framework" in lower:
        score += 8
    if re.search(r"\b(?:method|model|system|proposed|overall)\s+framework\b|\bframework\s+overview\b", lower):
        score += 12
    if re.search(r"(?:fig(?:ure)?\.?|图)\s*[12]\b", caption, flags=re.IGNORECASE):
        score += 3
    if any(term in lower for term in LOW_VALUE_TERMS):
        score -= 30
    if len(caption) > 700:
        score -= 20
    return max(score, 0.0)


def is_explicit_figure_caption(text: str) -> bool:
    return bool(re.match(r"^\s*(?:fig(?:ure)?\.?\s*\d+|图\s*\d+)[\s:：.．-]", text, flags=re.IGNORECASE))


def _resolve_image_path(raw_path: str, json_path: Path, mineru_dir: Path) -> Path | None:
    if not raw_path:
        return None
    candidates = [json_path.parent / raw_path, mineru_dir / raw_path, mineru_dir / "images" / Path(raw_path).name]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def _item_caption_candidates(item: dict[str, Any], following: list[dict[str, Any]]) -> list[str]:
    candidates = [clean_caption(item.get("image_caption") or item.get("caption"))]
    for next_item in following[:2]:
        if str(next_item.get("type") or "").lower() in {"image", "figure"}:
            break
        text = clean_caption(next_item.get("text") or next_item.get("image_caption") or next_item.get("caption"))
        if is_explicit_figure_caption(text):
            candidates.append(text)
            break
    return [candidate for candidate in candidates if candidate]


def _select_overview_from_mineru(
    stem: str,
    workspace_id: int | None,
    mineru_dir: Path,
    target_dir: str,
    high_confidence_only: bool = True,
) -> tuple[str, str, float]:
    best: tuple[float, Path | None, str] = (0.0, None, "")
    for json_path in mineru_dir.rglob("*content_list*.json"):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for index, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").lower() in {"image", "figure"}:
                image_path = _resolve_image_path(str(item.get("img_path") or item.get("image_path") or ""), json_path, mineru_dir)
                if not image_path:
                    continue
                following = [next_item for next_item in data[index + 1 : index + 3] if isinstance(next_item, dict)]
                for caption in _item_caption_candidates(item, following):
                    score = score_overview_caption(caption)
                    if score > best[0]:
                        best = (score, image_path, caption)
    if not best[1]:
        return "", "", 0.0
    if high_confidence_only and best[0] < MIN_OVERVIEW_SCORE:
        return "", best[2], best[0]
    figure_dir = workspace_root(workspace_id) / target_dir
    target = figure_dir / f"{stem}-overview{best[1].suffix.lower() or '.jpg'}"
    shutil.copy2(best[1], target)
    return workspace_relative_path(target), best[2], best[0]


def select_overview_from_mineru(candidate: SearchCandidate, mineru_dir: Path) -> tuple[str, str]:
    figure_path, caption, _score = _select_overview_from_mineru(
        candidate_stem(candidate),
        candidate.workspace_id,
        mineru_dir,
        "candidates/figures",
    )
    return figure_path, caption


async def parse_candidate_assets(candidate: SearchCandidate) -> None:
    candidate.parse_status = "parsing"
    candidate.parse_error = ""
    pdf_text = ""
    try:
        pdf_relative = await download_candidate_pdf(candidate)
        candidate.pdf_file_path = pdf_relative
        pdf_path = get_settings().knowledge_base_dir / pdf_relative if pdf_relative else None
        settings = get_settings()
        if pdf_path and settings.mineru_api_base and settings.mineru_api_token:
            mineru_dir = workspace_root(candidate.workspace_id) / "cache" / "mineru" / candidate_stem(candidate)
            pdf_text = await _extract_pdf_text_with_mineru_api(pdf_path, mineru_dir, timeout=settings.mineru_timeout)
            figure_path, caption = select_overview_from_mineru(candidate, mineru_dir)
            candidate.overview_figure_path = figure_path
            candidate.overview_caption = caption
        candidate.initial_parse_markdown = make_initial_parse_markdown(candidate, pdf_text)
        candidate.parse_status = "parsed"
    except Exception as exc:  # noqa: BLE001 - candidate preview should survive partial parse failures
        candidate.initial_parse_markdown = make_initial_parse_markdown(candidate, pdf_text)
        candidate.parse_status = "failed"
        candidate.parse_error = str(exc)


def paper_mineru_cache_dirs(paper: Paper) -> list[Path]:
    settings = get_settings()
    project_root = Path(__file__).resolve().parents[3]
    stem = paper_stem(paper)
    return [
        workspace_root(paper.workspace_id) / "cache" / "mineru" / stem,
        settings.knowledge_base_dir.resolve() / "cache" / "mineru" / stem,
        project_root / "data" / "mineru_cache" / stem,
    ]


async def download_paper_pdf(paper: Paper, timeout: int = 90) -> str:
    if paper.pdf_file_path:
        existing = get_settings().knowledge_base_dir.resolve() / paper.pdf_file_path
        if existing.exists() and existing.is_file():
            return paper.pdf_file_path
    if not paper.pdf:
        return ""
    target = workspace_root(paper.workspace_id) / "papers" / "pdf" / f"{paper_stem(paper)}.pdf"
    if not target.exists() or target.stat().st_size <= 0:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ResearchWorkspace/0.1)"}
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = await client.get(paper.pdf)
            response.raise_for_status()
        target.write_bytes(response.content)
    return workspace_relative_path(target)


async def backfill_paper_overviews(
    db: Session,
    workspace_id: int | None = None,
    force: bool = False,
    parse_missing: bool = False,
    high_confidence_only: bool = True,
) -> dict[str, Any]:
    settings = get_settings()
    papers = list(db.scalars(select(Paper).where(Paper.workspace_id == workspace_id).order_by(Paper.id)).all())
    result: dict[str, Any] = {
        "total": len(papers),
        "updated": 0,
        "already_had": 0,
        "low_confidence": 0,
        "missing_pdf": 0,
        "download_failed": 0,
        "mineru_failed": 0,
        "missing": 0,
        "failed": 0,
        "errors": [],
        "selected": [],
        "skipped": [],
    }
    for paper in papers:
        if paper.overview_figure_path and not force:
            result["already_had"] += 1
            continue
        try:
            figure_path = ""
            caption = ""
            score = 0.0
            reparse_failed = False
            if parse_missing and settings.mineru_api_base and settings.mineru_api_token:
                try:
                    pdf_relative = await download_paper_pdf(paper)
                    paper.pdf_file_path = pdf_relative or paper.pdf_file_path
                except Exception as exc:  # noqa: BLE001 - preserve batch progress
                    result["download_failed"] += 1
                    reparse_failed = True
                    if len(result["errors"]) < 8:
                        result["errors"].append({"paper_id": paper.id, "title": paper.title, "stage": "download", "error": describe_exception(exc)})
                    pdf_relative = ""
                if pdf_relative:
                    try:
                        pdf_path = settings.knowledge_base_dir.resolve() / pdf_relative
                        cache_dir = workspace_root(paper.workspace_id) / "cache" / "mineru" / paper_stem(paper)
                        await _extract_pdf_text_with_mineru_api(pdf_path, cache_dir, timeout=settings.mineru_timeout)
                    except Exception as exc:  # noqa: BLE001 - fall back to any existing cache
                        result["mineru_failed"] += 1
                        reparse_failed = True
                        if len(result["errors"]) < 8:
                            result["errors"].append({"paper_id": paper.id, "title": paper.title, "stage": "mineru", "error": describe_exception(exc)})
                elif not reparse_failed:
                    result["missing_pdf"] += 1
            for cache_dir in paper_mineru_cache_dirs(paper):
                if not cache_dir.exists():
                    continue
                figure_path, caption, score = _select_overview_from_mineru(
                    paper_stem(paper),
                    paper.workspace_id,
                    cache_dir,
                    "assets/figures",
                    high_confidence_only=high_confidence_only,
                )
                if figure_path:
                    break
            if figure_path:
                paper.overview_figure_path = figure_path
                paper.overview_caption = caption
                result["updated"] += 1
                result["selected"].append({"paper_id": paper.id, "title": paper.title, "score": score, "caption": caption})
            elif caption:
                if force:
                    paper.overview_figure_path = ""
                    paper.overview_caption = ""
                result["low_confidence"] += 1
                result["skipped"].append({"paper_id": paper.id, "title": paper.title, "score": score, "caption": caption})
            else:
                if force:
                    paper.overview_figure_path = ""
                    paper.overview_caption = ""
                result["missing"] += 1
        except Exception as exc:  # noqa: BLE001 - continue backfilling the rest
            result["failed"] += 1
            if len(result["errors"]) < 8:
                result["errors"].append({"paper_id": paper.id, "title": paper.title, "stage": "unknown", "error": describe_exception(exc)})
    db.commit()
    return result


def candidate_from_search_item(run_id: int, workspace_id: int | None, item: dict[str, Any]) -> SearchCandidate:
    tags = item.get("tags") or infer_tags(str(item.get("title") or ""), str(item.get("abstract") or ""))
    data = {**item, "tags": tags}
    priority = item.get("priority") or infer_priority(data)
    return SearchCandidate(
        workspace_id=workspace_id,
        run_id=run_id,
        key=item.get("key") or stable_key(str(item.get("title") or ""), item.get("ids") or {}),
        title=item.get("title") or "Untitled",
        authors=item.get("authors") or [],
        year=item.get("year"),
        venue=item.get("venue") or "",
        source=item.get("source") or "",
        sources=item.get("sources") or ([item.get("source")] if item.get("source") else []),
        ids=item.get("ids") or {},
        url=item.get("url") or "",
        pdf=item.get("pdf") or "",
        abstract=item.get("abstract") or "",
        abstract_zh=item.get("abstract_zh") or "",
        project_url=item.get("project_url") or project_url_from_mapping(item),
        tags=tags,
        priority=priority,
        comment=item.get("comment") or short_comment({**data, "priority": priority}),
        parse_status="pending",
        status="pending",
    )


def ingest_candidate(db: Session, candidate: SearchCandidate) -> Paper:
    paper = db.scalar(select(Paper).where(Paper.workspace_id == candidate.workspace_id, Paper.key == candidate.key))
    if paper is None:
        paper = Paper(workspace_id=candidate.workspace_id, key=candidate.key, title=candidate.title)
        db.add(paper)
    paper.title = candidate.title
    paper.authors = candidate.authors or []
    paper.year = candidate.year
    paper.venue = candidate.venue
    paper.source = candidate.source
    paper.sources = candidate.sources or []
    paper.ids = candidate.ids or {}
    paper.url = candidate.url
    paper.pdf = candidate.pdf
    paper.abstract = candidate.abstract
    paper.abstract_zh = candidate.abstract_zh
    paper.project_url = candidate.project_url
    paper.pdf_file_path = promote_candidate_file(candidate, candidate.pdf_file_path, "papers/pdf")
    paper.overview_figure_path = promote_candidate_file(candidate, candidate.overview_figure_path, "assets/figures")
    paper.overview_caption = candidate.overview_caption
    paper.initial_parse_markdown = candidate.initial_parse_markdown or make_initial_parse_markdown(candidate)
    paper.tags = candidate.tags or []
    paper.status = "accepted"
    paper.reading_status = "candidate"
    paper.priority = candidate.priority or "B"
    paper.comment = candidate.comment
    db.flush()
    candidate.paper_id = paper.id
    candidate.status = "ingested"
    upsert_paper_chunks(db, paper)
    return paper
