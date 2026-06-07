from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import Paper, PaperChunk
from app.services.text import split_chunks


def upsert_paper_chunks(db: Session, paper: Paper) -> None:
    db.query(PaperChunk).filter(PaperChunk.paper_id == paper.id).delete()
    sources = [
        ("metadata", f"{paper.title}\n{', '.join(paper.authors or [])}\n{paper.year or ''} {paper.venue or paper.source}"),
        ("abstract", f"{paper.abstract}\n\n{paper.abstract_zh}"),
        ("initial_parse", paper.initial_parse_markdown or ""),
        ("deep_note", paper.note_markdown or ""),
    ]
    for chunk_type, text in sources:
        for chunk in split_chunks(text):
            db.add(PaperChunk(workspace_id=paper.workspace_id, paper_id=paper.id, chunk_type=chunk_type, content=chunk))
