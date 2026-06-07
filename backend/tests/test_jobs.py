from app.services.jobs import format_job_error


class EmptyMessageError(Exception):
    pass


def test_format_job_error_keeps_exception_type_when_message_is_empty() -> None:
    assert format_job_error(EmptyMessageError()) == "EmptyMessageError"


def test_format_job_error_keeps_exception_type_and_message() -> None:
    assert format_job_error(RuntimeError("failed to parse")) == "RuntimeError: failed to parse"

