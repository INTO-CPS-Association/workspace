"""FastAPI application factory for workspace admin."""

import os
from typing import Any, Dict

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

from admin.services import load_services


def create_app(path_prefix: str = "") -> FastAPI:
    """Create and configure the FastAPI application."""
    if path_prefix:
        path_prefix = path_prefix.strip("/")
        if path_prefix:
            path_prefix = f"/{path_prefix}"
    else:
        path_prefix = ""

    fastapi_app = FastAPI(
        title="Workspace Admin Service",
        description="Service discovery and management for DTaaS workspace",
        version="0.1.0",
    )

    router = APIRouter()

    @router.get("/")
    async def root() -> Dict[str, Any]:
        return {
            "service": "Workspace Admin Service",
            "version": "0.1.0",
            "endpoints": {
                "/services": "Get list of available workspace services",
                "/health": "Health check endpoint",
            },
        }

    @router.get("/services")
    async def get_services() -> JSONResponse:
        services = load_services(os.environ.get("PATH_PREFIX", ""))
        return JSONResponse(content=services)

    @router.get("/health")
    async def health_check() -> Dict[str, str]:
        return {"status": "healthy"}

    fastapi_app.include_router(router, prefix=path_prefix)
    return fastapi_app
