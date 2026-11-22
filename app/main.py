"""Punto de entrada de la API Digiverso."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.api.v1.categories import router as categories_router
from app.cache.category_tree import InMemoryCategoryTreeCache
from app.core.config import Settings, get_settings
from app.core.responses import ApiResponse, ok
from app.domain.exceptions import CatalogError
from app.repository.audit import SQLiteAuditRepository
from app.repository.categories import SQLiteCategoryRepository
from app.repository.database import Database
from app.services.categories import CategoryService


def create_app(settings: Settings | None = None) -> FastAPI:
    """Fábrica de aplicación; facilita pruebas con bases de datos aisladas."""

    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        database = Database(settings.database_path)
        application.state.settings = settings
        application.state.database = database
        application.state.category_service = CategoryService(
            repository=SQLiteCategoryRepository(database),
            audit_repository=SQLiteAuditRepository(database),
            cache=InMemoryCategoryTreeCache(),
            settings=settings,
        )
        yield

    application = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    @application.exception_handler(CatalogError)
    async def handle_catalog_error(_: object, exc: CatalogError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(
                {"message": exc.message, "data": exc.details, "success": False}
            ),
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: object, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "message": "Datos de la petición inválidos.",
                "data": {"errores": jsonable_encoder(exc.errors())},
                "success": False,
            },
        )

    @application.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        _: object, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "message": str(exc.detail),
                "data": {},
                "success": False,
            },
        )

    application.include_router(categories_router)

    @application.get(
        "/",
        tags=["Salud"],
        response_model=ApiResponse[dict[str, str]],
        summary="Comprobación de salud",
    )
    def root() -> ApiResponse[dict[str, str]]:
        return ok("Digiverso funcionando correctamente.", {"status": "ok"})

    return application


app = create_app()
