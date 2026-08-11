from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    ENGINEER = "engineer"
    ADMIN = "admin"


class Permission(StrEnum):
    SESSION_READ = "session:read"
    ANNOTATION_READ = "annotation:read"
    ANNOTATION_DRAFT = "annotation:draft"
    ANNOTATION_REVIEW = "annotation:review"
    ANNOTATION_WRITE = "annotation:write"  # Backwards-compatible capability alias.
    ANALYSIS_RUN = "analysis:run"
    RECOMMENDATION_APPROVE = "recommendation:approve"
    ADMINISTER = "system:administer"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset({Permission.SESSION_READ, Permission.ANNOTATION_READ}),
    Role.ANALYST: frozenset(
        {
            Permission.SESSION_READ,
            Permission.ANNOTATION_READ,
            Permission.ANNOTATION_DRAFT,
            Permission.ANNOTATION_WRITE,
            Permission.ANALYSIS_RUN,
        }
    ),
    Role.ENGINEER: frozenset(
        {
            Permission.SESSION_READ,
            Permission.ANNOTATION_READ,
            Permission.ANNOTATION_DRAFT,
            Permission.ANNOTATION_REVIEW,
            Permission.ANNOTATION_WRITE,
            Permission.ANALYSIS_RUN,
            Permission.RECOMMENDATION_APPROVE,
        }
    ),
    Role.ADMIN: frozenset(Permission),
}


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    roles: frozenset[Role]

    @property
    def permissions(self) -> frozenset[Permission]:
        return frozenset(permission for role in self.roles for permission in ROLE_PERMISSIONS[role])
