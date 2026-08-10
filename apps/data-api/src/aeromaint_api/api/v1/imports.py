from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from aeromaint_api.repositories import ImportJob, PostgresImportRepository
from aeromaint_api.security.dependencies import require
from aeromaint_api.security.models import Permission

router = APIRouter(
    prefix="/imports",
    tags=["imports"],
    dependencies=[Depends(require(Permission.SESSION_READ))],
)


class CreateImportRequest(BaseModel):
    source_uri: str = Field(min_length=1)


def get_import_repository(request: Request) -> PostgresImportRepository:
    repository = getattr(request.app.state, "import_repository", None)
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"
        )
    return cast(PostgresImportRepository, repository)


@router.post("", response_model=ImportJob, status_code=status.HTTP_201_CREATED)
async def create_import(
    body: CreateImportRequest,
    response: Response,
    idempotency_key: Annotated[str, Header(min_length=1)],
    repository: Annotated[PostgresImportRepository, Depends(get_import_repository)],
) -> ImportJob:
    job, created = await repository.create(idempotency_key, body.source_uri)
    if not created:
        response.status_code = status.HTTP_200_OK
    return job


@router.get("/{import_id}", response_model=ImportJob)
async def get_import(
    import_id: UUID,
    repository: Annotated[PostgresImportRepository, Depends(get_import_repository)],
) -> ImportJob:
    job = await repository.get(import_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="import not found")
    return job
