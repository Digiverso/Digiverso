"""Punto de entrada de la API Digiverso (autenticación + catálogo)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from app.api.auth_router import router as auth_router
from app.api.dependencies import build_auth_service
from app.api.errors import register_exception_handlers
from app.api.v1.admin_auth_parameters import router as admin_auth_parameters_router
from app.api.v1.admin_catalog_parameters import router as admin_catalog_parameters_router
from app.api.v1.admin_users import router as admin_users_router
from app.api.v1.categories import router as categories_router
from app.api.v1.commerce import router as commerce_router
from app.api.v1.media import router as media_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.products import router as products_router
from app.api.v1.publication_control import router as publication_control_router
from app.api.v1.showcase import router as showcase_router
from app.api.v1.users import router as users_router
from app.cache.auth_parameters import InMemoryAuthParametersCache
from app.cache.catalog_parameters import InMemoryCatalogParametersCache
from app.cache.category_tree import InMemoryCategoryTreeCache
from app.cache.showcase import InMemoryShowcaseCache
from app.core.config import Settings, get_settings, settings as default_settings
from app.core.responses import ApiResponse, ok
from app.domain.exceptions import CatalogError
from app.repository.audit import SQLiteAuditRepository
from app.repository.auth_parameters import SQLiteAuthParameterRepository
from app.repository.email_repository import build_notification_sender
from app.repository.events import InMemoryEventBus
from app.repository.notifications import notification_repository
from app.repository.categories import SQLiteCategoryRepository
from app.repository.auth_repository import auth_repository
from app.repository.commerce import SQLiteCommerceRepository
# Se importa después de las líneas compartidas para no colisionar con HU-11/HU-12.
from app.repository.catalog_parameters import SQLiteCatalogParameterRepository
from app.repository.database import Database
from app.repository.photo_storage import build_photo_storage
from app.repository.products import SQLiteProductRepository
from app.services.auth_parameters import AuthParametersService
from app.services.catalog_parameters import CatalogParametersService
from app.services.categories import CategoryService
from app.services.commerce import CommerceService
from app.services.media import MediaService
from app.services.notifications import NotificationService
from app.services.products import ProductService
from app.services.publication_control import PublicationControlService
from app.services.profile_service import ProfileService

DESCRIPTION = """
API REST de Digiverso con arquitectura de capas.

## Módulos

- **Autenticación**: registro, verificación de correo, sesión y perfil de usuario.
- **Roles y permisos**: asignación de roles (AUT-09) y consulta/validación de permisos.
- **Notificaciones**: preferencias, bandeja, lectura y cola de entrega (AUT-10/AUT-11).
- **Administración**: consulta y actualización versionada de los parámetros de autenticación.
- **Catálogo**: árbol de categorías, ciclo de vida de productos, medios del producto, búsqueda/vitrina y control de publicaciones (HU-11).
- **Comercio**: licencias de uso, descargas con URL firmada e historial de compras (HU-15).
- **Root**: estado del servicio.

Todas las respuestas usan el sobre `message`, `data` y `success`.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Fábrica de aplicación; facilita pruebas con bases de datos aisladas."""

    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        # HU-13: ``settings`` pasa a ser la vista que relee los parámetros CAT.
        nonlocal settings
        database = Database(settings.database_path)
        application.state.settings = settings
        application.state.database = database
        application.state.auth_parameters_service = AuthParametersService(
            repository=SQLiteAuthParameterRepository(database),
            audit_repository=SQLiteAuditRepository(database),
            cache=InMemoryAuthParametersCache(),
            settings=settings,
        )
        application.state.catalog_parameters_service = CatalogParametersService(
            repository=SQLiteCatalogParameterRepository(database),
            audit_repository=SQLiteAuditRepository(database),
            cache=InMemoryCatalogParametersCache(),
            settings=settings,
        )
        # Los consumidores del catálogo releen los parámetros vigentes en cada
        # operación a través de esta vista de Settings (HU-13). Se reasigna la
        # variable local para que todos los servicios creados después (incluidos
        # los de otras historias) reciban la misma vista sin tocar sus líneas.
        settings = application.state.catalog_parameters_service.settings_view
        application.state.settings = settings
        auth_service = build_auth_service(
            settings,
            parameters=application.state.auth_parameters_service,
        )
        photo_storage = build_photo_storage(settings)
        application.state.auth_service = auth_service
        application.state.photo_storage = photo_storage
        application.state.profile_service = ProfileService(
            repo=auth_service.repo,
            settings=settings,
            photo_storage=photo_storage,
            clock=auth_service.clock,
        )
        application.state.category_service = CategoryService(
            repository=SQLiteCategoryRepository(database),
            audit_repository=SQLiteAuditRepository(database),
            cache=InMemoryCategoryTreeCache(),
            settings=settings,
        )
        product_repository = SQLiteProductRepository(database)
        audit_repository = SQLiteAuditRepository(database)
        application.state.product_service = ProductService(
            repository=product_repository,
            category_repository=SQLiteCategoryRepository(database),
            audit_repository=audit_repository,
            settings=settings,
            showcase_cache=InMemoryShowcaseCache(),
            author_name_provider=lambda user_id: (
                account.nombre
                if (account := auth_repository.obtener_cuenta_por_id(user_id))
                else None
            ),
        )
        application.state.media_service = MediaService(
            repository=product_repository,
            audit_repository=audit_repository,
            settings=settings,
            showcase_cache=application.state.product_service.showcase_cache,
        )
        notification_service = NotificationService(
            repo=notification_repository,
            settings=settings,
            clock=auth_service.clock,
            sender=build_notification_sender(settings),
        )
        # No se expone como ``notifications_service``: el endpoint de bandeja
        # construye el suyo con el reloj de la sesión (HU-05/HU-11).
        event_bus = InMemoryEventBus()
        application.state.event_bus = event_bus
        application.state.publication_control_service = PublicationControlService(
            repository=product_repository,
            audit_repository=audit_repository,
            settings=settings,
            event_bus=event_bus,
            notifier=notification_service,
            clock=auth_service.clock,
            showcase_cache=application.state.product_service.showcase_cache,
        )
        application.state.commerce_service = CommerceService(
            repository=SQLiteCommerceRepository(database),
            product_repository=product_repository,
            audit_repository=audit_repository,
            settings=settings,
            clock=auth_service.clock,
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
                "name": "Administración · Parámetros del catálogo",
                "description": (
                    "Consulta, validación, versionamiento e historial de los parámetros "
                    "CAT-xx. Solo administradores con permiso explícito."
                ),
            },
            {
                "name": "Administración · Usuarios y roles",
                "description": (
                    "Asignación de roles permitidos por AUT-09 con auditoría y "
                    "protección del último administrador."
                ),
            },
            {
                "name": "Usuarios",
                "description": (
                    "Consulta y edición del perfil, y consulta de permisos efectivos."
                ),
            },
            {
                "name": "Usuarios · Notificaciones",
                "description": (
                    "Preferencias AUT-10, bandeja con retención AUT-11 y lectura "
                    "de notificaciones propias."
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
                "name": "Catálogo · Medios del producto",
                "description": "Carga y eliminación lógica de imágenes y videos.",
            },
            {
                "name": "Catálogo · Búsqueda y vitrina",
                "description": "Búsqueda, filtros, vitrina por categoría y detalle público.",
            },
            {
                "name": "Catálogo · Control de publicaciones",
                "description": "Cola de revisión, aprobación y rechazo con evidencia, evento y notificación.",
            },
            {
                "name": "Comercio · Licencias, descargas e historial",
                "description": (
                    "Licencias de uso, descargas con URL firmada (COM-08/COM-09) "
                    "e historial paginado de compras."
                ),
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
                {
                    "message": exc.message,
                    "data": {"codigo": exc.code, **exc.details},
                    "success": False,
                }
            ),
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errores = exc.errors()
        if request.url.path.startswith(
            (
                "/api/v1/auth",
                "/api/v1/admin/auth/",
                "/api/v1/admin/users",
                "/api/v1/users",
            )
        ):
            # Formato acordado en HU-01 y reutilizado por HU-03/HU-06: 400 con campo/mensaje.
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
    application.include_router(admin_catalog_parameters_router)
    application.include_router(admin_users_router)
    application.include_router(users_router)
    application.include_router(notifications_router)
    application.include_router(categories_router)
    application.include_router(products_router)
    application.include_router(media_router)
    application.include_router(showcase_router)
    application.include_router(publication_control_router)
    application.include_router(commerce_router)

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
