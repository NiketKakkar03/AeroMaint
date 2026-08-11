from fastapi import APIRouter

from aeromaint_api.api.v1.annotations import router as annotations_router
from aeromaint_api.api.v1.documents import router as documents_router
from aeromaint_api.api.v1.exports import router as exports_router
from aeromaint_api.api.v1.health import router as health_router
from aeromaint_api.api.v1.imports import router as imports_router
from aeromaint_api.api.v1.sessions import router as sessions_router
from aeromaint_api.api.v1.transport import router as transport_router

router = APIRouter(prefix="/v1")
router.include_router(sessions_router)
router.include_router(imports_router)
router.include_router(transport_router)
router.include_router(annotations_router)
router.include_router(exports_router)
router.include_router(health_router)
router.include_router(documents_router)
