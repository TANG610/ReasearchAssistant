from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api import routes
from app.db.base import Base
from app.models.entities import Paper


def test_get_paper_translates_missing_chinese_abstract(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        paper = Paper(
            key="title:needs-zh",
            title="Needs Chinese Abstract",
            abstract="This is an English abstract.",
            abstract_zh="",
        )
        db.add(paper)
        db.commit()
        db.refresh(paper)

        monkeypatch.setattr(routes, "translate_abstract_zh_sync", lambda abstract: f"中文：{abstract}")

        result = routes.get_paper(paper.id, db, None)
        saved = db.scalar(select(Paper).where(Paper.id == paper.id))

        assert result.abstract_zh == "中文：This is an English abstract."
        assert saved is not None
        assert saved.abstract_zh == "中文：This is an English abstract."
