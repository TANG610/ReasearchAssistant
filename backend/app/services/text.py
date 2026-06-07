import hashlib
import re


def normalize_title(title: str) -> str:
    text = re.sub(r"\s+", " ", title or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def stable_key(title: str, ids: dict | None = None) -> str:
    ids = ids or {}
    for field in ("arxiv", "doi", "semantic_scholar"):
        value = ids.get(field)
        if value:
            return f"{field}:{str(value).lower()}"
    digest = hashlib.sha1(normalize_title(title).encode("utf-8")).hexdigest()[:12]
    return f"title:{digest}"


def split_chunks(text: str, max_chars: int = 1800) -> list[str]:
    clean = re.sub(r"\n{3,}", "\n\n", text or "").strip()
    if not clean:
        return []
    paragraphs = clean.split("\n\n")
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = paragraph[:max_chars]
    if current:
        chunks.append(current)
    return chunks
