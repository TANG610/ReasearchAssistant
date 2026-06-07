from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = Path("/data/paper-agent/knowledge_base")


def normalize_note_path(note_path: str, title: str, key: str) -> str:
    source = Path(note_path) if note_path else Path()
    name = source.name
    if not name:
        fallback = (key or title or "untitled").replace(":", "-").replace("/", "-").replace("\\", "-")
        name = f"{fallback}.md"
    return (Path("papers") / "notes" / name).as_posix()


def load_library(source: Path) -> dict[str, Any]:
    path = source / "data" / "library.json"
    if not path.exists():
        raise FileNotFoundError(f"未找到旧知识库元数据：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def transformed_library(source: Path) -> tuple[dict[str, Any], dict[str, int]]:
    library = load_library(source)
    papers = library.get("papers") or {}
    missing_notes = 0
    for paper in papers.values():
        old_note = paper.get("note_path") or ""
        if old_note and not (source / old_note).exists():
            missing_notes += 1
        paper["note_path"] = normalize_note_path(old_note, paper.get("title") or "", paper.get("key") or "")
    return library, {"papers": len(papers), "missing_old_notes": missing_notes}


def ensure_dirs(target: Path, apply: bool) -> list[Path]:
    dirs = [
        target / "papers" / "pdf",
        target / "papers" / "notes",
        target / "indexes",
        target / "reports",
        target / "assets" / "figures",
        target / "cache" / "pdf_text",
        target / "cache" / "mineru",
        target / "metadata",
    ]
    if apply:
        for path in dirs:
            path.mkdir(parents=True, exist_ok=True)
    return dirs


def copy_tree_contents(source: Path, target: Path, apply: bool) -> int:
    if not source.exists():
        return 0
    files = [path for path in source.rglob("*") if path.is_file()]
    if apply:
        for path in files:
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    return len(files)


def copy_files(source: Path, target: Path, pattern: str, apply: bool) -> int:
    if not source.exists():
        return 0
    files = list(source.glob(pattern))
    if apply:
        target.mkdir(parents=True, exist_ok=True)
        for path in files:
            shutil.copy2(path, target / path.name)
    return len(files)


def write_metadata(library: dict[str, Any], target: Path, apply: bool) -> None:
    if not apply:
        return
    metadata_dir = target / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / "library.json").write_text(json.dumps(library, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def migrate(source: Path, target: Path, apply: bool, include_notes: bool, include_mineru_cache: bool) -> dict[str, Any]:
    library, library_stats = transformed_library(source)
    dirs = ensure_dirs(target, apply)
    write_metadata(library, target, apply)

    counts: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "source": str(source),
        "target": str(target),
        "created_dirs": [str(path) for path in dirs],
        "papers": library_stats["papers"],
        "missing_old_notes": library_stats["missing_old_notes"],
        "metadata_files": 1,
        "notes_copied": 0,
        "indexes_copied": copy_files(source / "Indexes", target / "indexes", "*.md", apply),
        "reports_copied": copy_files(source / "Reports", target / "reports", "*.md", apply),
        "figures_copied": copy_tree_contents(source / "Assets" / "Figures", target / "assets" / "figures", apply),
        "pdfs_copied": copy_files(source / "data" / "pdf_cache", target / "papers" / "pdf", "*.pdf", apply),
        "mineru_cache_files_copied": 0,
        "notes_policy": "skipped by default; regenerate with the web app",
    }
    if include_notes:
        counts["notes_copied"] = copy_files(source / "Papers", target / "papers" / "notes", "*.md", apply)
        counts["notes_policy"] = "copied because --include-notes was set"
    if include_mineru_cache:
        counts["mineru_cache_files_copied"] = copy_tree_contents(source / "data" / "mineru_cache", target / "cache" / "mineru", apply)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate the old project-local knowledge base into an external directory.")
    parser.add_argument("--source", default=str(ROOT), help="old project root that contains data/library.json")
    parser.add_argument("--target", default=str(DEFAULT_TARGET), help="external knowledge base directory")
    parser.add_argument("--apply", action="store_true", help="write files; without this flag only prints a dry-run report")
    parser.add_argument("--include-notes", action="store_true", help="copy old Markdown notes; default is to skip them")
    parser.add_argument("--include-mineru-cache", action="store_true", help="copy old MinerU cache; default is to regenerate it")
    args = parser.parse_args()

    result = migrate(
        Path(args.source).resolve(),
        Path(args.target).resolve(),
        apply=args.apply,
        include_notes=args.include_notes,
        include_mineru_cache=args.include_mineru_cache,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
