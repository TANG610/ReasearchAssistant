import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.entities import Paper
from app.services.knowledge_base import export_markdown, import_knowledge_base
from app.services.paper_metadata import extract_project_url


def test_import_metadata_without_old_notes_and_export_new_markdown(tmp_path: Path) -> None:
    kb = tmp_path / "knowledge_base"
    metadata_dir = kb / "metadata"
    metadata_dir.mkdir(parents=True)
    note_path = "papers/notes/example.md"
    (metadata_dir / "library.json").write_text(
        json.dumps(
            {
                "version": 1,
                "papers": {
                    "title:example": {
                        "key": "title:example",
                        "title": "Example Paper",
                        "authors": ["Ada"],
                        "year": 2026,
                        "venue": "arXiv",
                        "source": "arXiv",
                        "ids": {},
                        "url": "https://example.com/paper",
                        "pdf": "https://example.com/paper.pdf",
                        "abstract": "A test abstract.",
                        "abstract_zh": "测试中文摘要。",
                        "project_url": "https://github.com/example/project",
                        "tags": ["paper", "3dgs"],
                        "status": "candidate",
                        "reading_status": "candidate",
                        "priority": "A",
                        "note_path": note_path,
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        result = import_knowledge_base(db, kb)
        paper = db.scalar(select(Paper).where(Paper.key == "title:example"))
        assert result["imported"] == 1
        assert result["notes_found"] == 0
        assert paper is not None
        assert paper.title == "Example Paper"
        assert paper.priority == "A"
        assert paper.abstract_zh == "测试中文摘要。"
        assert paper.project_url == "https://github.com/example/project"
        assert paper.note_path == note_path
        assert paper.note_markdown == ""

        export_result = export_markdown(db, kb)
        assert export_result["exported"] == 1
        exported = kb / "papers" / "notes" / "example.md"
        assert exported.exists()
        exported_text = exported.read_text(encoding="utf-8")
        assert "abstract_zh: 测试中文摘要。" in exported_text
        assert "project_url: https://github.com/example/project" in exported_text
        assert "A test abstract." in exported_text


def test_import_requires_existing_knowledge_base_dir(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        with pytest.raises(FileNotFoundError, match="知识库目录不存在"):
            import_knowledge_base(db, tmp_path / "missing")


def test_extract_project_url_prefers_github() -> None:
    text = "Project page is available at https://example.org/demo. Code: https://github.com/demo/paper."

    assert extract_project_url(text) == "https://github.com/demo/paper"
