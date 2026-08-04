from fastapi import APIRouter

from aeromaint_api.api.v1.sessions import router as sessions_router

router = APIRouter(prefix="/v1")
router.include_router(sessions_router)
