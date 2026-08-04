from fastapi import APIRouter, HTTPException, status

from aeromaint_api.domain.fixtures import FIXTURE_MANIFEST, FIXTURE_SESSION_ID
from aeromaint_api.domain.manifest import CaptureSessionManifest

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/{session_id}/manifest", response_model=CaptureSessionManifest)
async def get_session_manifest(session_id: str) -> CaptureSessionManifest:
    if session_id != FIXTURE_SESSION_ID:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "session_not_found", "session_id": session_id},
        )
    return FIXTURE_MANIFEST
