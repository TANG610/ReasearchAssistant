from __future__ import annotations

import re
from typing import Any

import httpx

from app.core.config import get_settings


URL_RE = re.compile(r"https?://[^\s<>)\]\"']+", re.IGNORECASE)
PROJECT_HINT_RE = re.compile(r"(code|github|project\s+page|available\s+at|homepage|website)", re.IGNORECASE)
SKIP_HOSTS = (
    "arxiv.org",
    "openaccess.thecvf.com",
    "openreview.net",
    "semanticscholar.org",
    "doi.org",
)


def _clean_url(url: str) -> str:
    return url.rstrip(".,;:)]}>'\"")


def extract_project_url(*texts: str | None) -> str:
    candidates: list[str] = []
    for text in texts:
        if not text:
            continue
        candidates.extend(_clean_url(match.group(0)) for match in URL_RE.finditer(text))

    for url in candidates:
        if "github.com" in url.lower():
            return url

    for text in texts:
        if not text:
            continue
        for match in URL_RE.finditer(text):
            url = _clean_url(match.group(0))
            window = text[max(0, match.start() - 80) : min(len(text), match.end() + 80)]
            lower_url = url.lower()
            if any(host in lower_url for host in SKIP_HOSTS) or lower_url.endswith(".pdf"):
                continue
            if PROJECT_HINT_RE.search(window):
                return url
    return ""


def project_url_from_mapping(data: dict[str, Any], *fallback_texts: str | None) -> str:
    for field in ("project_url", "github_url", "github", "code_url", "repo_url", "homepage", "website"):
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            return _clean_url(value.strip())
    return extract_project_url(
        data.get("abstract") if isinstance(data.get("abstract"), str) else "",
        data.get("note_markdown") if isinstance(data.get("note_markdown"), str) else "",
        data.get("comment") if isinstance(data.get("comment"), str) else "",
        *fallback_texts,
    )


async def translate_abstract_zh(abstract: str) -> str:
    settings = get_settings()
    if not settings.deepseek_api_key or not abstract.strip():
        return ""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                json={
                    "model": settings.deepseek_model,
                    "messages": [
                        {"role": "system", "content": "你是严谨的论文摘要翻译助手。只输出中文译文，不添加点评。"},
                        {"role": "user", "content": abstract},
                    ],
                    "temperature": 0.1,
                },
            )
            response.raise_for_status()
        data: dict[str, Any] = response.json()
        return str(data["choices"][0]["message"]["content"]).strip()
    except Exception:
        return ""


def translate_abstract_zh_sync(abstract: str) -> str:
    settings = get_settings()
    if not settings.deepseek_api_key or not abstract.strip():
        return ""
    try:
        with httpx.Client(timeout=60) as client:
            response = client.post(
                f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                json={
                    "model": settings.deepseek_model,
                    "messages": [
                        {"role": "system", "content": "你是严谨的论文摘要翻译助手。只输出中文译文，不添加点评。"},
                        {"role": "user", "content": abstract},
                    ],
                    "temperature": 0.1,
                },
            )
            response.raise_for_status()
        data: dict[str, Any] = response.json()
        return str(data["choices"][0]["message"]["content"]).strip()
    except Exception:
        return ""
