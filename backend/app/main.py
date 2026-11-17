"""FastAPI 应用入口。

统一错误封装：所有错误响应都带有 ``code`` 与 ``message``；
校验失败额外带 ``fields``（字段 → 错误类型/原始信息），便于前端给出友好提示。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import api_router

logger = logging.getLogger("ipms")

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="知识产权管理系统：专利、软件著作权、商标/Logo 档案与证书管理。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


def _field_path(loc: tuple) -> str:
    """把 Pydantic 的 loc 规约为字段名，去掉 body/query/path 等前缀。"""

    parts = [str(part) for part in loc if part not in {"body", "query", "path", "header", "cookie"}]
    return ".".join(parts) if parts else "request"


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """请求校验失败：返回字段级错误，前端据此高亮并给出中文提示。"""

    fields: dict[str, dict[str, str]] = {}
    for error in exc.errors():
        field = _field_path(error.get("loc", ()))
        fields.setdefault(
            field,
            {"type": error.get("type", "value_error"), "msg": error.get("msg", "")},
        )
    return JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "message": "输入校验失败",
            "detail": "输入校验失败",
            "fields": fields,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """业务异常：保留 ``detail`` 兼容既有调用，同时补齐 code/message。"""

    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": "business_error", "message": message, "detail": exc.detail},
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底异常：记录堆栈，对外只返回通用提示，不泄露内部细节。"""

    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"code": "internal_error", "message": "服务器内部错误", "detail": "服务器内部错误"},
    )


@app.get("/health", tags=["系统"])
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}
