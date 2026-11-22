from fastapi import FastAPI

from app.api.auth_router import router as auth_router
from app.api.errors import register_exception_handlers
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    description="API REST de Digiverso con arquitectura de capas.",
    version="1.0.0",
)

app.include_router(auth_router)
register_exception_handlers(app)


@app.get("/", tags=["Root"], summary="Estado de la API")
def root():
    return {
        "mensaje": "Digiverso funcionando correctamente",
        "docs": "/docs",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.app_port, reload=settings.app_debug)
