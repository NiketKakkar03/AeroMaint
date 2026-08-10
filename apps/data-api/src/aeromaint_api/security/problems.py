from collections.abc import Mapping
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


def problem_response(
    request: Request,
    status: int,
    code: str,
    title: str,
    detail: str,
    headers: Mapping[str, str] | None = None,
    extensions: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://aeromaint.dev/problems/{code}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "code": code,
    }
    if extensions:
        body.update(extensions)
    return JSONResponse(
        body,
        status_code=status,
        headers=dict(headers) if headers else None,
        media_type="application/problem+json",
    )
