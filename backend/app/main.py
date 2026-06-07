from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.routes import ensure_default_user, router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine


def ensure_schema_compat() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    dialect = engine.dialect.name
    table_additions = {
        "users": {
            "workspace_id": "INTEGER",
        },
        "papers": {
            "workspace_id": "INTEGER",
            "abstract_zh": "TEXT DEFAULT ''",
            "project_url": "TEXT DEFAULT ''",
            "pdf_file_path": "TEXT DEFAULT ''",
            "overview_figure_path": "TEXT DEFAULT ''",
            "overview_caption": "TEXT DEFAULT ''",
            "initial_parse_markdown": "TEXT DEFAULT ''",
        },
        "paper_notes": {"workspace_id": "INTEGER"},
        "paper_chunks": {"workspace_id": "INTEGER"},
        "search_runs": {"workspace_id": "INTEGER"},
        "search_results": {"workspace_id": "INTEGER"},
        "jobs": {"workspace_id": "INTEGER"},
        "chat_sessions": {"workspace_id": "INTEGER"},
        "ideas": {"workspace_id": "INTEGER"},
    }
    with engine.begin() as connection:
        for table, additions in table_additions.items():
            if table not in tables:
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for column, column_type in additions.items():
                if column in existing:
                    continue
                if dialect == "postgresql":
                    statement = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {column_type}"
                else:
                    statement = f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"
                connection.execute(text(statement))


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix=settings.api_prefix)

    @app.on_event("startup")
    def startup() -> None:
        Base.metadata.create_all(bind=engine)
        ensure_schema_compat()
        db = SessionLocal()
        try:
            ensure_default_user(db)
        finally:
            db.close()

    return app


app = create_app()
