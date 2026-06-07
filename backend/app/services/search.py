from __future__ import annotations

import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.paper_metadata import project_url_from_mapping, translate_abstract_zh
from app.services.text import stable_key


def _year_from_text(text: str) -> int | None:
    match = re.search(r"\b(20\d{2})\b", text or "")
    return int(match.group(1)) if match else None


async def search_arxiv(query: str, limit: int) -> list[dict[str, Any]]:
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": limit,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get("https://export.arxiv.org/api/query", params=params)
        response.raise_for_status()

    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(response.text)
    results: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", ns):
        title = " ".join((entry.findtext("atom:title", default="", namespaces=ns) or "").split())
        url = entry.findtext("atom:id", default="", namespaces=ns) or ""
        arxiv_id = url.rsplit("/", 1)[-1] if url else ""
        abstract = " ".join((entry.findtext("atom:summary", default="", namespaces=ns) or "").split())
        authors = [node.findtext("atom:name", default="", namespaces=ns) or "" for node in entry.findall("atom:author", ns)]
        pdf = ""
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "pdf":
                pdf = link.attrib.get("href", "")
        ids = {"arxiv": arxiv_id} if arxiv_id else {}
        results.append(
            {
                "key": stable_key(title, ids),
                "title": title,
                "authors": [item for item in authors if item],
                "year": _year_from_text(entry.findtext("atom:published", default="", namespaces=ns) or ""),
                "venue": "arXiv",
                "source": "arXiv",
                "sources": ["arXiv"],
                "ids": ids,
                "url": url,
                "pdf": pdf or (f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""),
                "abstract": abstract,
                "tags": ["paper"],
                "status": "candidate",
                "reading_status": "candidate",
                "priority": "B",
                "comment": "通过关键词搜索发现，需人工筛选。",
            }
        )
    return results


async def search_papers(query: str, sources: list[str], limit: int) -> list[dict[str, Any]]:
    normalized = {source.lower() for source in sources}
    if normalized - {"arxiv"}:
        kb_results = run_existing_kb_search(query, list(normalized), limit)
        if kb_results:
            return await enrich_paper_metadata(kb_results)
    if "arxiv" in normalized:
        return await enrich_paper_metadata(await search_arxiv(query, limit))
    return []


async def enrich_paper_metadata(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for paper in papers:
        paper.setdefault("abstract_zh", "")
        paper.setdefault("project_url", "")
        if not paper["project_url"]:
            paper["project_url"] = project_url_from_mapping(paper)
        if not paper["abstract_zh"] and paper.get("abstract"):
            paper["abstract_zh"] = await translate_abstract_zh(str(paper["abstract"]))
    return papers


def run_existing_kb_search(query: str, sources: list[str], limit: int) -> list[dict[str, Any]]:
    settings = get_settings()
    project_root = Path(__file__).resolve().parents[3]
    knowledge_base_dir = Path(settings.knowledge_base_dir).resolve()
    workspace = knowledge_base_dir / "cache" / "search_workspace"
    script = project_root / "Scripts" / "kb.py"
    if not script.exists():
        return []
    cli_sources = [source for source in sources if source in {"arxiv", "cvf", "openreview"}]
    cmd = [
        sys.executable,
        str(script),
        "--vault",
        str(workspace),
        "search",
        "--query",
        query,
        "--limit",
        str(limit),
        "--sources",
        *cli_sources,
    ]
    result = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=180, check=False)
    if result.returncode != 0:
        return []
    candidates_path = workspace / "data" / "candidates.json"
    if not candidates_path.exists():
        return []
    import json

    data = json.loads(candidates_path.read_text(encoding="utf-8"))
    papers = data.get("papers") or []
    for paper in papers:
        paper.setdefault("key", stable_key(paper.get("title", ""), paper.get("ids") or {}))
        paper.setdefault("status", "candidate")
        paper.setdefault("reading_status", paper.get("status", "candidate"))
        paper.setdefault("priority", "B")
        paper.setdefault("tags", ["paper"])
        paper.setdefault("sources", [paper.get("source", "")] if paper.get("source") else [])
        paper.setdefault("abstract_zh", "")
        paper.setdefault("project_url", project_url_from_mapping(paper))
    return papers[:limit]
