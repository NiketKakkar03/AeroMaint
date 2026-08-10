from dataclasses import dataclass


@dataclass(slots=True)
class SecurityError(Exception):
    status: int
    code: str
    title: str
    detail: str
    headers: dict[str, str] | None = None
