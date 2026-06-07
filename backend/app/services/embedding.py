from __future__ import annotations

import math

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import PaperChunk


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


async def qwen_embed(texts: list[str], dimensions: int = 1024) -> list[list[float]]:
    settings = get_settings()
    if not settings.dashscope_api_key or not texts:
        return []
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
            headers={"Authorization": f"Bearer {settings.dashscope_api_key}"},
            json={
                "model": settings.qwen_embedding_model,
                "input": texts,
                "dimensions": dimensions,
                "encoding_format": "float",
            },
        )
        response.raise_for_status()
    data = response.json()
    return [item["embedding"] for item in sorted(data.get("data", []), key=lambda item: item.get("index", 0))]


async def ensure_chunk_embeddings(db: Session, chunks: list[PaperChunk]) -> None:
    pending = [chunk for chunk in chunks if not chunk.embedding and chunk.content.strip()]
    for start in range(0, len(pending), 10):
        batch = pending[start : start + 10]
        vectors = await qwen_embed([chunk.content[:6000] for chunk in batch])
        for chunk, vector in zip(batch, vectors, strict=False):
            chunk.embedding = vector
    if pending:
        db.commit()
