from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.auth import DomainError


def _envelope(message: str, data: Any, success: bool = False) -> dict[str, Any]:
    return {"message": message, "data": data, "success": success}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.message, exc.data),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        detalles = []
        for error in exc.errors():
            campo = ".".join(str(parte) for parte in error.get("loc", ()) if parte not in {"body", "query", "path"})
            detalles.append({"campo": campo, "mensaje": error.get("msg", "Dato inválido")})
        return JSONResponse(
            status_code=400,
            content=_envelope(
                "La petición contiene datos inválidos.",
                {"codigo": "validacion", "detalle": detalles},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        mensaje = exc.detail if isinstance(exc.detail, str) else "Error en la petición."
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(mensaje, {"codigo": "http_error"}),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=_envelope("Error interno del servidor.", {"codigo": "error_interno"}),
        )
