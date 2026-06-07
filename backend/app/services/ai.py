from __future__ import annotations

import hashlib
import io
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import Paper, PaperChunk
from app.services.embedding import cosine_similarity, ensure_chunk_embeddings, qwen_embed
from app.services.text import stable_key


STOPWORDS = {"和", "与", "及", "有什么", "什么", "关系", "区别", "联系", "the", "and", "or", "of"}
DEEP_READ_MAX_CHARS = 80000
PDF_TEXT_MIN_CHARS = 1000


def query_terms(query: str) -> list[str]:
    raw_terms = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-_.]*|[\u4e00-\u9fff]{2,}", query)
    terms = []
    for term in raw_terms:
        normalized = term.strip().lower()
        if normalized and normalized not in STOPWORDS:
            terms.append(normalized)
    return terms


def _lexical_scores(papers: list[Paper], terms: list[str]) -> dict[int, int]:
    scores: dict[int, int] = {}
    if not terms:
        return scores
    for paper in papers:
        title = (paper.title or "").lower()
        abstract = (paper.abstract or "").lower()
        initial_parse = (paper.initial_parse_markdown or "").lower()
        note = (paper.note_markdown or "").lower()
        tags = " ".join(paper.tags or []).lower()
        score = 0
        for term in terms:
            if term in title:
                score += 10
            if term in tags:
                score += 4
            if term in abstract:
                score += 3
            if term in initial_parse:
                score += 2
            if term in note:
                score += 2
        if score:
            scores[paper.id] = score
    return scores


async def retrieve_context(db: Session, query: str, limit: int = 5, workspace_id: int | None = None) -> list[Paper]:
    terms = query_terms(query)
    papers = list(db.scalars(select(Paper).where(Paper.workspace_id == workspace_id)).all())
    paper_by_id = {paper.id: paper for paper in papers}
    combined: dict[int, float] = {paper_id: float(score) for paper_id, score in _lexical_scores(papers, terms).items()}

    query_vector = (await qwen_embed([query]))[:1]
    if query_vector:
        chunks = list(db.scalars(select(PaperChunk).where(PaperChunk.workspace_id == workspace_id).limit(500)).all())
        await ensure_chunk_embeddings(db, chunks)
        for chunk in chunks:
            if chunk.embedding:
                combined[chunk.paper_id] = combined.get(chunk.paper_id, 0.0) + cosine_similarity(query_vector[0], chunk.embedding) * 8

    if not combined:
        return papers[:limit]
    ranked = sorted(
        ((score, paper_by_id[paper_id]) for paper_id, score in combined.items() if paper_id in paper_by_id),
        key=lambda item: (-item[0], item[1].priority, -(item[1].year or 0), item[1].title),
    )
    return [paper for _, paper in ranked[:limit]]


async def deepseek_chat(messages: list[dict[str, str]]) -> str:
    settings = get_settings()
    if not settings.deepseek_api_key:
        return ""
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json={"model": settings.deepseek_model, "messages": messages, "temperature": 0.3},
        )
        response.raise_for_status()
    data: dict[str, Any] = response.json()
    return data["choices"][0]["message"]["content"]


def _slugify(text: str, limit: int = 80) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return (slug[:limit].strip("-") or "paper")


def _paper_cache_stem(paper: Paper) -> str:
    key = paper.key or stable_key(paper.title, paper.ids)
    safe_key = key.replace(":", "-").replace("/", "-")
    return f"{safe_key}-{_slugify(paper.title, limit=64)}"


def _workspace_root(knowledge_base_dir: Path, workspace_id: int | None) -> Path:
    return knowledge_base_dir / "workspaces" / str(workspace_id or 1)


def mineru_cache_dir(knowledge_base_dir: Path, paper: Paper) -> Path:
    return _workspace_root(knowledge_base_dir, paper.workspace_id) / "cache" / "mineru" / _paper_cache_stem(paper)


def legacy_mineru_cache_dir(knowledge_base_dir: Path, paper: Paper) -> Path:
    return knowledge_base_dir / "cache" / "mineru" / _paper_cache_stem(paper)


def pdf_cache_path(knowledge_base_dir: Path, paper: Paper) -> Path:
    if paper.pdf_file_path:
        existing = knowledge_base_dir / paper.pdf_file_path
        if existing.exists() and existing.is_file():
            return existing
    return _workspace_root(knowledge_base_dir, paper.workspace_id) / "papers" / "pdf" / f"{_paper_cache_stem(paper)}.pdf"


def normalize_pdf_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _read_mineru_full_text(knowledge_base_dir: Path, paper: Paper) -> tuple[str, str] | None:
    candidates = [mineru_cache_dir(knowledge_base_dir, paper) / "full.md", legacy_mineru_cache_dir(knowledge_base_dir, paper) / "full.md"]
    full_md = next((path for path in candidates if path.exists()), None)
    if full_md is None:
        return None
    text = normalize_pdf_text(full_md.read_text(encoding="utf-8", errors="replace"))
    if len(text) < PDF_TEXT_MIN_CHARS:
        return None
    return text, str(full_md)


def _write_mineru_full_text(knowledge_base_dir: Path, paper: Paper, text: str) -> Path:
    full_md = mineru_cache_dir(knowledge_base_dir, paper) / "full.md"
    full_md.parent.mkdir(parents=True, exist_ok=True)
    full_md.write_text(normalize_pdf_text(text), encoding="utf-8")
    return full_md


async def _download_pdf(paper: Paper, target: Path, timeout: int) -> Path:
    if target.exists() and target.stat().st_size > 0:
        return target
    if not paper.pdf:
        raise RuntimeError("这篇论文没有 PDF 链接，无法进行 PDF 精读。")
    target.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(paper.pdf)
        response.raise_for_status()
    target.write_bytes(response.content)
    return target


def _mineru_payload(pdf_path: Path) -> dict[str, Any]:
    settings = get_settings()
    return {
        "enable_formula": settings.mineru_enable_formula,
        "enable_table": settings.mineru_enable_table,
        "language": settings.mineru_language,
        "files": [
            {
                "name": pdf_path.name,
                "is_ocr": settings.mineru_is_ocr,
                "data_id": hashlib.sha1(str(pdf_path).encode("utf-8")).hexdigest()[:16],
            }
        ],
    }


def _mineru_data(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data")
    return data if isinstance(data, dict) else response


def _mineru_result_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("extract_result", "extract_results", "results", "files"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _mineru_status_done(status: str) -> bool:
    return status.lower() in {"done", "success", "succeeded", "completed", "complete"}


def _mineru_status_failed(status: str) -> bool:
    return status.lower() in {"failed", "fail", "error", "canceled", "cancelled"}


def _safe_extract_mineru_zip(zip_bytes: bytes, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    root = output_dir.resolve()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            target = (output_dir / member.filename).resolve()
            if root not in target.parents and target != root:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as dest:
                shutil.copyfileobj(source, dest)


def _mineru_zip_markdown(zip_bytes: bytes, output_dir: Path) -> str:
    _safe_extract_mineru_zip(zip_bytes, output_dir)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = archive.namelist()
        preferred = [name for name in names if name.endswith("full.md")]
        markdown_names = preferred or [name for name in names if name.lower().endswith(".md")]
        if not markdown_names:
            raise RuntimeError("MinerU result zip does not contain Markdown.")
        chunks = [archive.read(name).decode("utf-8", errors="replace") for name in markdown_names[:5]]
    return normalize_pdf_text("\n\n".join(chunks))


async def _extract_pdf_text_with_mineru_api(pdf_path: Path, output_dir: Path, timeout: int) -> str:
    settings = get_settings()
    base_url = settings.mineru_api_base.strip().rstrip("/")
    token = settings.mineru_api_token.strip()
    if not base_url or not token:
        raise RuntimeError("MINERU_API_BASE or MINERU_API_TOKEN is not configured.")

    api_timeout = settings.mineru_timeout or timeout
    poll_interval = settings.mineru_poll_interval or 3.0
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=api_timeout, follow_redirects=True) as client:
        created_response = await client.post(f"{base_url}/file-urls/batch", headers=headers, json=_mineru_payload(pdf_path))
        created_response.raise_for_status()
        created = _mineru_data(created_response.json())

        batch_id = str(created.get("batch_id") or created.get("batchId") or "")
        file_urls = created.get("file_urls") or created.get("fileUrls") or created.get("urls") or []
        if not batch_id or not isinstance(file_urls, list) or not file_urls:
            raise RuntimeError("MinerU task response is missing batch_id or file_urls.")
        first_file = file_urls[0] if isinstance(file_urls[0], dict) else {"url": file_urls[0]}
        upload_url = str(first_file.get("url") or first_file.get("upload_url") or first_file.get("uploadUrl") or "")
        if not upload_url:
            raise RuntimeError("MinerU task response is missing upload URL.")

        upload_response = await client.put(upload_url, content=pdf_path.read_bytes())
        upload_response.raise_for_status()

        deadline = time.monotonic() + api_timeout
        last_status = ""
        while time.monotonic() < deadline:
            poll_response = await client.get(f"{base_url}/extract-results/batch/{batch_id}", headers=headers)
            poll_response.raise_for_status()
            poll_data = _mineru_data(poll_response.json())
            items = _mineru_result_items(poll_data)
            if not items:
                last_status = str(poll_data.get("status") or poll_data.get("state") or "")
                await _sleep(poll_interval)
                continue

            item = items[0]
            last_status = str(item.get("state") or item.get("status") or poll_data.get("state") or poll_data.get("status") or "")
            full_zip_url = str(item.get("full_zip_url") or item.get("fullZipUrl") or item.get("zip_url") or item.get("zipUrl") or "")
            markdown_url = str(item.get("markdown_url") or item.get("markdownUrl") or item.get("md_url") or "")
            markdown = item.get("markdown") or item.get("md")

            if _mineru_status_failed(last_status):
                message = item.get("err_msg") or item.get("message") or item.get("error") or "unknown error"
                raise RuntimeError(f"MinerU parsing failed: {message}")
            if not _mineru_status_done(last_status):
                await _sleep(poll_interval)
                continue
            if full_zip_url:
                zip_response = await client.get(full_zip_url, headers={"Authorization": f"Bearer {token}"})
                zip_response.raise_for_status()
                text = _mineru_zip_markdown(zip_response.content, output_dir)
            elif markdown_url:
                markdown_response = await client.get(markdown_url, headers={"Authorization": f"Bearer {token}"})
                markdown_response.raise_for_status()
                text = normalize_pdf_text(markdown_response.text)
            elif markdown:
                text = normalize_pdf_text(str(markdown))
            else:
                raise RuntimeError("MinerU completed but did not return Markdown.")

            if len(text) < PDF_TEXT_MIN_CHARS:
                raise RuntimeError("MinerU Markdown is too short, parsing may have failed.")
            return text
    raise RuntimeError(f"MinerU parsing timed out, last status: {last_status or 'unknown'}")


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


def _extract_pdf_text_with_command(pdf_path: Path, command_name: str, tool_kind: str, timeout: int) -> str:
    if tool_kind == "pdftotext":
        command = [command_name, "-enc", "UTF-8", str(pdf_path), "-"]
    else:
        command = [command_name, "draw", "-F", "txt", "-o", "-", str(pdf_path)]
    result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=timeout, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"{tool_kind} PDF 文本抽取失败：{detail or '外部工具返回非零退出码'}")
    text = normalize_pdf_text(result.stdout)
    if len(text) < PDF_TEXT_MIN_CHARS:
        raise RuntimeError(f"{tool_kind} PDF 文本抽取结果太短，可能是扫描版 PDF 或抽取工具不可用。")
    return text


def _available_pdf_text_tools() -> list[tuple[str, str]]:
    tools: list[tuple[str, str]] = []
    for command_name, tool_kind in (("pdftotext", "pdftotext"), ("mutool", "mutool")):
        resolved = shutil.which(command_name)
        if resolved:
            tools.append((resolved, tool_kind))
    return tools


async def extract_deep_read_pdf_text(paper: Paper, timeout: int = 120) -> tuple[str, str]:
    settings = get_settings()
    knowledge_base_dir = settings.knowledge_base_dir.resolve()
    cached = _read_mineru_full_text(knowledge_base_dir, paper)
    if cached:
        return cached

    pdf_path = await _download_pdf(paper, pdf_cache_path(knowledge_base_dir, paper), timeout=timeout)
    failures: list[str] = []
    parser = settings.pdf_parser.strip().lower()
    should_try_mineru = parser in {"", "auto", "mineru", "mineru-api", "mineru-precise"} and bool(
        settings.mineru_api_base and settings.mineru_api_token
    )
    if should_try_mineru:
        try:
            cache_dir = mineru_cache_dir(knowledge_base_dir, paper)
            text = await _extract_pdf_text_with_mineru_api(pdf_path, cache_dir, timeout=max(timeout, settings.mineru_timeout))
            full_md = _write_mineru_full_text(knowledge_base_dir, paper, text)
            return text, f"mineru:{full_md}"
        except Exception as exc:  # noqa: BLE001 - local tools can still rescue simple PDFs
            failures.append(f"MinerU: {exc}")

    tools = _available_pdf_text_tools()
    if not tools:
        detail = "；".join(failures) if failures else "没有可用工具。"
        raise RuntimeError(f"未找到可用的 PDF 文本抽取工具。请检查 MinerU 配置，或安装 pdftotext / mutool。\n{detail}")

    for command_name, tool_kind in tools:
        try:
            text = _extract_pdf_text_with_command(pdf_path, command_name, tool_kind, timeout=timeout)
            return text, f"{tool_kind}:{pdf_path}"
        except Exception as exc:  # noqa: BLE001 - report all extractor failures together
            failures.append(str(exc))
    detail = "；".join(failures) if failures else "没有可用工具。"
    raise RuntimeError(f"PDF 文本抽取失败：{detail}")


def clean_existing_note_excerpt(markdown: str, max_chars: int = 2500) -> str:
    lines: list[str] = []
    skip_section = False
    for raw_line in (markdown or "").splitlines():
        line = raw_line.rstrip()
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            title = heading.group(1)
            skip_section = title in {"待读问题", "读后问题回答"}
            if skip_section:
                continue
        if skip_section and line.startswith("## "):
            skip_section = False
        if skip_section:
            continue
        if "待补充" in line or "待精读后回答" in line:
            continue
        lines.append(line)
    return normalize_pdf_text("\n".join(lines))[:max_chars]


def deep_read_messages(paper: Paper, pdf_text: str, source: str, note_excerpt: str) -> list[dict[str, str]]:
    clipped = pdf_text[:DEEP_READ_MAX_CHARS]
    meta = (
        f"标题：{paper.title}\n"
        f"作者：{'、'.join(paper.authors or [])}\n"
        f"年份：{paper.year or '未知'}\n"
        f"会议/来源：{paper.venue or paper.source or '未知'}\n"
        f"英文摘要：{paper.abstract or '无'}\n"
        f"中文摘要：{paper.abstract_zh or '无'}\n"
        f"PDF 文本来源：{source}"
    )
    existing_note = note_excerpt or "无可用人工笔记。"
    prompt = (
        "请用中文精读这篇论文，输出 Markdown。必须主要依据 PDF 文本，不要把已有笔记模板当作论文事实。"
        "请包含这些二级标题：核心问题、方法一句话、输入输出、关键模块、实验设置、主要结论、局限/风险、"
        "可复用点、精读可信度。关键模块要写清楚每个模块的作用、输入、输出、流程、公式或训练细节。"
        "不要编造 PDF 中没有的信息，不确定时写“待人工确认”。\n\n"
        f"论文元数据：\n{meta}\n\n"
        f"已有人工笔记摘录（只作参考，可能包含旧模板）：\n{existing_note}\n\n"
        f"PDF 正文节选（最多 {DEEP_READ_MAX_CHARS} 字符）：\n{clipped}"
    )
    return [
        {"role": "system", "content": "你是严谨的论文精读助手，只根据用户提供的 PDF 正文和元数据总结。"},
        {"role": "user", "content": prompt},
    ]


def _paper_context_chunks(db: Session, paper: Paper, limit: int = 4) -> list[PaperChunk]:
    preferred = {"deep_note": 0, "initial_parse": 1, "abstract": 2, "metadata": 3}
    chunks = list(db.scalars(select(PaperChunk).where(PaperChunk.paper_id == paper.id)).all())
    return sorted(chunks, key=lambda chunk: (preferred.get(chunk.chunk_type, 9), chunk.id))[:limit]


async def answer_with_rag(db: Session, question: str, workspace_id: int | None = None) -> tuple[str, list[dict[str, Any]]]:
    papers = await retrieve_context(db, question, workspace_id=workspace_id)
    citation_rows: list[dict[str, Any]] = []
    context_blocks: list[str] = []
    for index, paper in enumerate(papers, start=1):
        chunks = _paper_context_chunks(db, paper)
        source_types = sorted({chunk.chunk_type for chunk in chunks})
        citation_rows.append({"paper_id": paper.id, "title": paper.title, "url": paper.url, "sources": source_types})
        chunk_text = "\n\n".join(f"来源：{chunk.chunk_type}\n{chunk.content[:1200]}" for chunk in chunks)
        context_blocks.append(f"[{index}] {paper.title}\n{chunk_text}")
    citations = citation_rows
    context = "\n\n".join(context_blocks)
    if context:
        answer = await deepseek_chat(
            [
                {"role": "system", "content": "你是科研学习助手。回答要简洁、明确，并优先引用给定论文上下文。"},
                {"role": "user", "content": f"问题：{question}\n\n论文上下文：\n{context}"},
            ]
        )
        if answer:
            return answer, citations
    fallback = "我先基于本地库做了关键词检索，但当前没有配置 DeepSeek API，所以下面只给出相关论文线索：\n"
    if not papers:
        fallback += "没有找到明显相关的论文。"
    else:
        fallback += "\n".join(f"- {paper.title}（{paper.year or '未知年份'} / {paper.venue or paper.source}）" for paper in papers)
    return fallback, citations


async def make_deep_read_note(paper: Paper) -> str:
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY，无法执行 AI 精读。请配置后重新触发。")
    pdf_text, source = await extract_deep_read_pdf_text(paper)
    note_excerpt = clean_existing_note_excerpt(paper.note_markdown)
    answer = await deepseek_chat(deep_read_messages(paper, pdf_text, source, note_excerpt))
    if answer:
        return answer
    raise RuntimeError("DeepSeek 没有返回精读内容。")
