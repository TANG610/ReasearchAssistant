from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.entities import Paper  # noqa: E402
from app.services.candidates import backfill_paper_overviews  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-run PDF parsing and backfill high-confidence overview figures.")
    parser.add_argument("--workspace-id", type=int, default=None, help="Workspace id to process. Defaults to every workspace with papers.")
    parser.add_argument("--cache-only", action="store_true", help="Use existing MinerU cache only; do not download PDFs or call MinerU.")
    parser.add_argument("--no-force", action="store_true", help="Keep existing overview figures instead of overwriting them.")
    parser.add_argument("--allow-low-confidence", action="store_true", help="Allow the best available figure even below the overview confidence threshold.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    with SessionLocal() as db:
        if args.workspace_id is None:
            workspace_ids = [row[0] for row in db.execute(select(Paper.workspace_id).distinct()).all()]
        else:
            workspace_ids = [args.workspace_id]
        merged = {
            "total": 0,
            "updated": 0,
            "already_had": 0,
            "low_confidence": 0,
            "missing_pdf": 0,
            "download_failed": 0,
            "mineru_failed": 0,
            "missing": 0,
            "failed": 0,
            "errors": [],
            "selected": [],
            "skipped": [],
        }
        for workspace_id in workspace_ids:
            result = await backfill_paper_overviews(
                db,
                workspace_id=workspace_id,
                force=not args.no_force,
                parse_missing=not args.cache_only,
                high_confidence_only=not args.allow_low_confidence,
            )
            print(json.dumps({"workspace_id": workspace_id, **result}, ensure_ascii=False, indent=2))
            for key in ["total", "updated", "already_had", "low_confidence", "missing_pdf", "download_failed", "mineru_failed", "missing", "failed"]:
                merged[key] += int(result.get(key, 0))
            merged["errors"].extend(result.get("errors", []))
            merged["selected"].extend(result.get("selected", []))
            merged["skipped"].extend(result.get("skipped", []))
        print(json.dumps({"merged": merged}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
