from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.api.dependencies import get_client_ip, get_current_account, get_profile_service
from app.core.config import Settings
from app.core.responses import ApiResponse, ok
from app.domain.auth import Account, UpdatePerfilRequest, UserProfile
from app.domain.profile import InvalidProfileError, validar_tamano
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/api/v1/users", tags=["Usuarios"])

CAMPOS_EDITABLES = {"nombre", "biografia", "foto"}

_PROPIEDADES_JSON = {
    "nombre": {"type": "string", "nullable": True, "minLength": 2, "maxLength": 100},
    "biografia": {"type": "string", "nullable": True, "maxLength": 500},
    "foto": {
        "type": "string",
        "nullable": True,
        "description": "Data URL base64 o URL https de una imagen permitida (AUT-12)",
    },
}
_REQUEST_BODY = {
    "required": True,
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "properties": _PROPIEDADES_JSON,
                "additionalProperties": False,
            }
        },
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string"},
                    "biografia": {"type": "string"},
                    "foto": {"type": "string", "format": "binary"},
                },
            }
        },
    },
}


def _rechazar_campos_no_editables(payload: dict[str, Any]) -> None:
    campos = sorted(set(payload) - CAMPOS_EDITABLES)
    if campos:
        campo = campos[0]
        raise InvalidProfileError(
            f"El campo '{campo}' no es editable desde el perfil.",
            campo=campo,
        )


def _validar_payload(payload: dict[str, Any]) -> UpdatePerfilRequest:
    try:
        return UpdatePerfilRequest.model_validate(payload)
    except ValidationError as exc:
        primer_error = exc.errors()[0]
        campo = ".".join(
            str(parte) for parte in primer_error.get("loc", ()) if parte != "body"
        ) or "body"
        raise InvalidProfileError(
            "El perfil contiene datos inválidos.",
            campo=campo,
            detalles={"mensaje": primer_error.get("msg", "Dato inválido")},
        ) from exc


async def parse_cambios_perfil(request: Request) -> UpdatePerfilRequest:
    tipo_contenido = request.headers.get("content-type", "").lower()
    settings: Settings = request.app.state.settings
    payload: dict[str, Any]

    if tipo_contenido.startswith("multipart/form-data"):
        payload = {}
        form = await request.form()
        for clave, valor in form.multi_items():
            if clave not in CAMPOS_EDITABLES:
                _rechazar_campos_no_editables({clave: valor})
            if clave == "foto" and isinstance(valor, StarletteUploadFile):
                if not valor.filename:
                    continue
                contenido = await valor.read(settings.profile_photo_max_bytes + 1)
                validar_tamano(contenido, settings.profile_photo_max_bytes)
                payload["foto"] = contenido
            else:
                payload[clave] = valor
    else:
        crudo = await request.body()
        if not crudo:
            payload = {}
        else:
            try:
                payload = json.loads(crudo)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise InvalidProfileError(
                    "El cuerpo de la petición no es JSON válido.",
                    campo="body",
                ) from exc
            if not isinstance(payload, dict):
                raise InvalidProfileError(
                    "El cuerpo de la petición debe ser un objeto.",
                    campo="body",
                )

    _rechazar_campos_no_editables(payload)
    return _validar_payload(payload)


@router.get(
    "/me",
    response_model=ApiResponse[UserProfile],
    status_code=status.HTTP_200_OK,
    summary="Consultar perfil propio (FUN-07 / PRC-07)",
    description="Devuelve los datos permitidos del usuario autenticado, sin campos sensibles.",
    responses={
        401: {"description": "Token de acceso ausente, inválido, expirado o sin sesión activa"},
    },
)
def consultar_perfil(
    cuenta: Account = Depends(get_current_account),
    service: ProfileService = Depends(get_profile_service),
) -> ApiResponse[UserProfile]:
    return ok("Perfil consultado correctamente.", service.consultar(cuenta))


@router.patch(
    "/me",
    response_model=ApiResponse[UserProfile],
    status_code=status.HTTP_200_OK,
    summary="Editar perfil propio (FUN-08 / PRC-08)",
    description=(
        "Actualiza nombre, biografía o foto. Acepta JSON (data URL o URL de CDN) y "
        "multipart/form-data. Rechaza rol, correo, estado y cualquier otro usuario."
    ),
    responses={
        400: {"description": "Campo no editable, dato inválido o foto fuera de AUT-12"},
        401: {"description": "Token de acceso ausente, inválido, expirado o sin sesión activa"},
    },
    openapi_extra={"requestBody": _REQUEST_BODY},
)
def editar_perfil(
    cambios: UpdatePerfilRequest = Depends(parse_cambios_perfil),
    cuenta: Account = Depends(get_current_account),
    service: ProfileService = Depends(get_profile_service),
    ip: str = Depends(get_client_ip),
) -> ApiResponse[UserProfile]:
    return ok(
        "Perfil actualizado correctamente.",
        service.actualizar(cuenta=cuenta, cambios=cambios, ip=ip),
    )


@router.api_route("/{cuenta_id}", methods=["GET", "PATCH"], include_in_schema=False)
def perfil_ajeno(cuenta_id: str) -> None:
    raise HTTPException(status_code=404, detail="El perfil solicitado no existe.")
