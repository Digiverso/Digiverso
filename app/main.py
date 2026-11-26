"""Punto de entrada de la API Digiverso (autenticación + catálogo)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from app.api.auth_router import router as auth_router
from app.api.errors import register_exception_handlers
from app.api.v1.admin_auth_parameters import router as admin_auth_parameters_router
from app.api.v1.categories import router as categories_router
from app.api.v1.products import router as products_router
from app.cache.auth_parameters import InMemoryAuthParametersCache
from app.cache.category_tree import InMemoryCategoryTreeCache
from app.core.config import Settings, get_settings, settings as default_settings
from app.core.responses import ApiResponse, ok
from app.domain.exceptions import CatalogError
from app.repository.audit import SQLiteAuditRepository
from app.repository.auth_parameters import SQLiteAuthParameterRepository
from app.repository.categories import SQLiteCategoryRepository
from app.repository.database import Database
from app.repository.products import SQLiteProductRepository
from app.services.auth_parameters import AuthParametersService
from app.services.categories import CategoryService
from app.services.products import ProductService

DESCRIPTION = """
API REST de Digiverso con arquitectura de capas.

## Módulos

- **Autenticación**: registro, verificación de correo e inicio de sesión.
- **Administración**: consulta y actualización versionada de los parámetros de autenticación.
- **Catálogo**: gestión del árbol de categorías y ciclo de vida de productos.
- **Root**: estado del servicio.

Todas las respuestas usan el sobre `message`, `data` y `success`.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Fábrica de aplicación; facilita pruebas con bases de datos aisladas."""

    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        database = Database(settings.database_path)
        application.state.settings = settings
        application.state.database = database
        application.state.auth_parameters_service = AuthParametersService(
            repository=SQLiteAuthParameterRepository(database),
            audit_repository=SQLiteAuditRepository(database),
            cache=InMemoryAuthParametersCache(),
            settings=settings,
        )
        application.state.category_service = CategoryService(
            repository=SQLiteCategoryRepository(database),
            audit_repository=SQLiteAuditRepository(database),
            cache=InMemoryCategoryTreeCache(),
            settings=settings,
        )
        application.state.product_service = ProductService(
            repository=SQLiteProductRepository(database),
            category_repository=SQLiteCategoryRepository(database),
            audit_repository=SQLiteAuditRepository(database),
            settings=settings,
        )
        yield

    application = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version="1.0.0",
        contact={"name": "Soporte Digiverso", "email": "soporte@example.com"},
        license_info={"name": "Proyecto académico"},
        openapi_tags=[
            {
                "name": "Autenticación",
                "description": "Registro de visitantes, verificación de cuenta y acceso.",
            },
            {
                "name": "Administración · Parámetros de autenticación",
                "description": (
                    "Consulta, validación, versionamiento e historial de los parámetros "
                    "AUT-xx. Solo administradores con permiso explícito."
                ),
            },
            {
                "name": "Catálogo · Categorías",
                "description": "Creación, edición, desactivación y consulta del árbol.",
            },
            {
                "name": "Catálogo · Productos",
                "description": "Creación, edición, revisión, archivo y reactivación.",
            },
            {
                "name": "Root",
                "description": "Información básica del servicio.",
            },
        ],
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        swagger_ui_parameters={
            "deepLinking": True,
            "displayRequestDuration": True,
            "persistAuthorization": True,
            "filter": True,
            "tryItOutEnabled": True,
        },
        debug=settings.app_debug,
        lifespan=lifespan,
    )

    # Manejadores de HU-01 (DomainError, HTTPException y Exception).
    register_exception_handlers(application)

    @application.exception_handler(CatalogError)
    async def handle_catalog_error(_: Request, exc: CatalogError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(
                {"message": exc.message, "data": exc.details, "success": False}
            ),
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errores = exc.errors()
        if request.url.path.startswith(("/api/v1/auth", "/api/v1/admin/auth/")):
            # Formato acordado en HU-01 y reutilizado por HU-06: 400 con campo/mensaje.
            detalle = [
                {
                    "campo": ".".join(
                        str(parte)
                        for parte in error.get("loc", ())
                        if parte not in {"body", "query", "path"}
                    ),
                    "mensaje": error.get("msg", "Dato inválido"),
                }
                for error in errores
            ]
            return JSONResponse(
                status_code=400,
                content={
                    "message": "La petición contiene datos inválidos.",
                    "data": {"codigo": "validacion", "detalle": detalle},
                    "success": False,
                },
            )

        # Formato de catálogo: 422 con la lista original de errores.
        return JSONResponse(
            status_code=422,
            content={
                "message": "Datos de la petición inválidos.",
                "data": {"errores": jsonable_encoder(errores)},
                "success": False,
            },
        )

    application.include_router(auth_router)
    application.include_router(admin_auth_parameters_router)
    application.include_router(categories_router)
    application.include_router(products_router)

    @application.get(
        "/",
        tags=["Root"],
        response_model=ApiResponse[dict[str, str]],
        summary="Estado de la API",
    )
    def root() -> ApiResponse[dict[str, str]]:
        return ok(
            "Digiverso funcionando correctamente.",
            {"docs": "/docs", "version": "1.0.0", "status": "ok"},
        )

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=default_settings.app_port,
        reload=default_settings.app_debug,
    )
