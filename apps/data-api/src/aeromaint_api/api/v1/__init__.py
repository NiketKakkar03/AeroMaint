from fastapi import APIRouter

from aeromaint_api.api.v1.imports import router as imports_router
from aeromaint_api.api.v1.sessions import router as sessions_router
from aeromaint_api.api.v1.transport import router as transport_router

router = APIRouter(prefix="/v1")
router.include_router(sessions_router)
router.include_router(imports_router)
router.include_router(transport_router)
