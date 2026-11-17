"""API 路由汇总。"""

from fastapi import APIRouter

from app.routers import admin, assets, auth, certificates, dates, fees, materials, meta, stats

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(assets.router)
api_router.include_router(certificates.router)
api_router.include_router(materials.router)
api_router.include_router(dates.router)
api_router.include_router(fees.router)
api_router.include_router(meta.router)
api_router.include_router(stats.router)
api_router.include_router(admin.router)

__all__ = ["api_router"]
