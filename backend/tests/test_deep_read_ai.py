import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.entities import Paper
from app.services import ai


def make_paper(**overrides) -> Paper:
    data = {
        "key": "title:abc123",
        "title": "Example Paper",
        "authors": ["Ada"],
        "year": 2026,
        "venue": "arXiv",
        "source": "arXiv",
        "ids": {},
        "url": "https://example.com/paper",
        "pdf": "https://example.com/paper.pdf",
        "abstract": "A short abstract.",
        "abstract_zh": "一段中文摘要。",
        "note_markdown": "",
    }
    data.update(overrides)
    return Paper(**data)


def settings(tmp_path: Path, api_key: str = "test-key") -> SimpleNamespace:
    return SimpleNamespace(
        knowledge_base_dir=tmp_path,
        deepseek_api_key=api_key,
        deepseek_base_url="https://api.deepseek.test",
        deepseek_model="deepseek-test",
        pdf_parser="auto",
        mineru_api_base="",
        mineru_api_token="",
        mineru_language="ch",
        mineru_enable_table=True,
        mineru_enable_formula=True,
        mineru_is_ocr=False,
        mineru_timeout=300,
        mineru_poll_interval=3.0,
    )


def test_extract_deep_read_pdf_text_prefers_mineru_full_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paper = make_paper()
    cache_dir = tmp_path / "cache" / "mineru" / "title-abc123-example-paper"
    cache_dir.mkdir(parents=True)
    full_text = "# Example Paper\n\n" + ("PDF evidence from MinerU. " * 80)
    (cache_dir / "full.md").write_text(full_text, encoding="utf-8")
    monkeypatch.setattr(ai, "get_settings", lambda: settings(tmp_path))

    text, source = asyncio.run(ai.extract_deep_read_pdf_text(paper))

    assert "PDF evidence from MinerU" in text
    assert source.endswith("full.md")


def test_extract_deep_read_pdf_text_uses_mineru_api_and_writes_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paper = make_paper()
    pdf_path = tmp_path / "papers" / "pdf" / "paper.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF test")
    parsed_text = "Parsed by MinerU API. " * 80
    local_settings = settings(tmp_path)
    local_settings.mineru_api_base = "https://mineru.test/api/v4"
    local_settings.mineru_api_token = "mineru-token"
    captured: dict[str, Path] = {}

    async def fake_download(_paper: Paper, _target: Path, timeout: int) -> Path:
        return pdf_path

    async def fake_mineru(path: Path, output_dir: Path, timeout: int) -> str:
        captured["pdf_path"] = path
        captured["output_dir"] = output_dir
        return parsed_text

    monkeypatch.setattr(ai, "get_settings", lambda: local_settings)
    monkeypatch.setattr(ai, "_download_pdf", fake_download)
    monkeypatch.setattr(ai, "_extract_pdf_text_with_mineru_api", fake_mineru)

    text, source = asyncio.run(ai.extract_deep_read_pdf_text(paper))

    assert "Parsed by MinerU API" in text
    assert source.startswith("mineru:")
    assert captured["pdf_path"] == pdf_path
    assert captured["output_dir"].name == "title-abc123-example-paper"
    assert (captured["output_dir"] / "full.md").exists()


def test_make_deep_read_note_requires_deepseek_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai, "get_settings", lambda: settings(tmp_path, api_key=""))

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        asyncio.run(ai.make_deep_read_note(make_paper()))


def test_make_deep_read_note_uses_pdf_text_and_filters_template(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paper = make_paper(
        note_markdown=(
            "# Example Paper\n\n"
            "## 核心问题\n\n"
            "待补充：这篇论文到底解决什么具体问题？\n\n"
            "## 读后问题回答\n\n"
            "- 待精读后回答：实验主要证明了什么？\n\n"
            "## 人工备注\n\n"
            "这是一条人工备注。"
        )
    )
    captured: dict[str, str] = {}

    async def fake_extract(_paper: Paper) -> tuple[str, str]:
        return "Real PDF evidence. " * 120, "test-full.md"

    async def fake_deepseek(messages: list[dict[str, str]]) -> str:
        captured["prompt"] = messages[-1]["content"]
        return "## 核心问题\n\n基于 PDF 的精读。"

    monkeypatch.setattr(ai, "get_settings", lambda: settings(tmp_path))
    monkeypatch.setattr(ai, "extract_deep_read_pdf_text", fake_extract)
    monkeypatch.setattr(ai, "deepseek_chat", fake_deepseek)

    result = asyncio.run(ai.make_deep_read_note(paper))

    assert "基于 PDF 的精读" in result
    assert "Real PDF evidence" in captured["prompt"]
    assert "这是一条人工备注" in captured["prompt"]
    assert "和我方向的关系" not in captured["prompt"]
    assert "待补充" not in captured["prompt"]
    assert "待精读后回答" not in captured["prompt"]
