from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass(frozen=True)
class ApiProblem(Exception):
    status: int
    code: str
    title: str
    detail: str
    extra: dict[str, Any] | None = None


def problem_response(request: Request, problem: ApiProblem) -> JSONResponse:
    request_id = request.state.request_id
    body: dict[str, Any] = {
        "type": f"https://aeromaint.dev/problems/{problem.code.lower()}",
        "title": problem.title,
        "status": problem.status,
        "detail": problem.detail,
        "instance": request.url.path,
        "code": problem.code,
        "request_id": request_id,
        "trace_id": request.state.trace_id,
    }
    if problem.extra:
        body.update(problem.extra)
    return JSONResponse(body, status_code=problem.status, media_type="application/problem+json")
