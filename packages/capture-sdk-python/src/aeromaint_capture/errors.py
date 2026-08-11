from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Problem:
    code: str | None = None
    title: str | None = None
    detail: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    type: str | None = None
    instance: str | None = None


class CaptureError(Exception):
    def __init__(self, message: str, *, code: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class CaptureHttpError(CaptureError):
    def __init__(self, status: int, problem: Problem, *, retryable: bool) -> None:
        message = problem.detail or problem.title or f"Capture API returned HTTP {status}"
        super().__init__(message, code=problem.code or "HTTP_ERROR", retryable=retryable)
        self.status = status
        self.problem = problem


class CaptureTransportError(CaptureError):
    pass
