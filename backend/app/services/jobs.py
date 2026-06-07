from sqlalchemy.orm import Session

from app.models.entities import Job


def format_job_error(error: Exception | str) -> str:
    if isinstance(error, Exception):
        error_type = type(error).__name__
        message = str(error).strip()
        return f"{error_type}: {message}" if message else error_type
    return str(error).strip() or "Unknown error"


def create_job(db: Session, job_type: str, payload: dict, workspace_id: int | None = None) -> Job:
    job = Job(workspace_id=workspace_id, type=job_type, status="running", payload=payload, result={}, error="")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def complete_job(db: Session, job: Job, result: dict) -> Job:
    job.status = "completed"
    job.result = result
    job.error = ""
    db.commit()
    db.refresh(job)
    return job


def fail_job(db: Session, job: Job, error: Exception | str) -> Job:
    job.status = "failed"
    job.error = format_job_error(error)
    db.commit()
    db.refresh(job)
    return job
