from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.domain.actor import Actor
from app.domain.auth import PermissionDeniedError, Role
from app.repository.auth_repository import auth_repository
from app.services.auth_service import AuthService
from app.services.roles_permissions import RolesPermissionsService
from tests.test_auth_session import crear_cuenta_verificada, iniciar_sesion

ADMIN_ROLES_URL = "/api/v1/admin/users"
PERMISSIONS_URL = "/api/v1/users/me/permissions"
CAMPOS_ASIGNACION = {"usuarioId", "rolAnterior", "rolNuevo"}
CAMPOS_PERMISOS = {"usuarioId", "rol", "permisos", "recursos"}


def _headers_sesion(client: TestClient) -> dict[str, str]:
    token = iniciar_sesion(client).json()["data"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _eventos(tipo: str) -> list:
    return [evento for evento in auth_repository.eventos_auditoria() if evento.tipo == tipo]


def test_asignacion_valida_actualiza_rol_y_audita(client: TestClient, email_gateway) -> None:
    cuenta_id = crear_cuenta_verificada(client, email_gateway)

    respuesta = client.post(
        f"{ADMIN_ROLES_URL}/{cuenta_id}/roles",
        json={"rol": "productor"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["success"] is True
    assert cuerpo["message"] == "Rol asignado correctamente."
    assert set(cuerpo["data"]) == CAMPOS_ASIGNACION
    assert cuerpo["data"] == {
        "usuarioId": cuenta_id,
        "rolAnterior": "consumidor",
        "rolNuevo": "productor",
    }
    assert auth_repository.obtener_cuenta_por_id(cuenta_id).rol is Role.PRODUCTOR

    eventos = _eventos("rol_asignado")
    assert len(eventos) == 1
    assert eventos[0].cuenta_id == cuenta_id
    assert eventos[0].metadata["rolAnterior"] == "consumidor"
    assert eventos[0].metadata["rolNuevo"] == "productor"
    assert eventos[0].metadata["actorId"] == "usr_admin"


def test_rol_no_permitido_devuelve_400_y_no_cambia(client: TestClient, email_gateway) -> None:
    cuenta_id = crear_cuenta_verificada(client, email_gateway)

    respuesta = client.post(
        f"{ADMIN_ROLES_URL}/{cuenta_id}/roles",
        json={"rol": "invalido"},
    )

    assert respuesta.status_code == 400
    cuerpo = respuesta.json()
    assert cuerpo["success"] is False
    assert cuerpo["data"]["codigo"] == "rol_no_permitido"
    assert auth_repository.obtener_cuenta_por_id(cuenta_id).rol is Role.CONSUMIDOR
    assert not _eventos("rol_asignado")
    assert _eventos("rol_asignacion_rechazada")[0].metadata["motivo"] == "rol_no_permitido"


def test_consumidor_con_cabeceras_no_puede_asignar_roles(
    client: TestClient, email_gateway
) -> None:
    cuenta_id = crear_cuenta_verificada(client, email_gateway)
    headers = {"X-Actor-Id": cuenta_id, "X-Actor-Roles": "consumidor"}

    respuesta = client.post(
        f"{ADMIN_ROLES_URL}/{cuenta_id}/roles",
        json={"rol": "administrador"},
        headers=headers,
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["data"]["codigo"] == "permiso_denegado"
    assert auth_repository.obtener_cuenta_por_id(cuenta_id).rol is Role.CONSUMIDOR
    rechazo = _eventos("rol_asignacion_rechazada")[0]
    assert rechazo.metadata["actorId"] == cuenta_id
    assert rechazo.metadata["motivo"] == "permiso_denegado"


def test_sesion_de_consumidor_no_puede_elevarse_con_cabeceras(
    client: TestClient, email_gateway
) -> None:
    cuenta_id = crear_cuenta_verificada(client, email_gateway)
    headers = _headers_sesion(client)
    headers["X-Actor-Roles"] = "administrador"

    respuesta = client.post(
        f"{ADMIN_ROLES_URL}/{cuenta_id}/roles",
        json={"rol": "administrador"},
        headers=headers,
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["data"]["codigo"] == "permiso_denegado"
    assert auth_repository.obtener_cuenta_por_id(cuenta_id).rol is Role.CONSUMIDOR


def test_token_invalido_no_cae_en_administrador_por_defecto(
    client: TestClient, email_gateway
) -> None:
    cuenta_id = crear_cuenta_verificada(client, email_gateway)

    respuesta = client.post(
        f"{ADMIN_ROLES_URL}/{cuenta_id}/roles",
        json={"rol": "productor"},
        headers={"Authorization": "Bearer token-invalido"},
    )

    assert respuesta.status_code == 401
    assert auth_repository.obtener_cuenta_por_id(cuenta_id).rol is Role.CONSUMIDOR
    assert not _eventos("rol_asignado")


def test_ultimo_administrador_no_puede_ser_degradado(
    client: TestClient, email_gateway
) -> None:
    cuenta_id = crear_cuenta_verificada(client, email_gateway)
    asignacion = client.post(
        f"{ADMIN_ROLES_URL}/{cuenta_id}/roles", json={"rol": "administrador"}
    )
    assert asignacion.status_code == 200

    respuesta = client.post(
        f"{ADMIN_ROLES_URL}/{cuenta_id}/roles", json={"rol": "consumidor"}
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["data"]["codigo"] == "ultimo_administrador"
    assert auth_repository.obtener_cuenta_por_id(cuenta_id).rol is Role.ADMINISTRADOR
    assert _eventos("rol_asignacion_rechazada")[0].metadata["motivo"] == "ultimo_administrador"


def test_asignacion_idempotente_no_duplica_cambio(
    client: TestClient, email_gateway
) -> None:
    cuenta_id = crear_cuenta_verificada(client, email_gateway)
    url = f"{ADMIN_ROLES_URL}/{cuenta_id}/roles"

    primera = client.post(url, json={"rol": "productor"})
    segunda = client.post(url, json={"rol": "productor"})

    assert primera.status_code == segunda.status_code == 200
    assert primera.json()["data"] == {
        "usuarioId": cuenta_id,
        "rolAnterior": "consumidor",
        "rolNuevo": "productor",
    }
    assert segunda.json()["data"] == {
        "usuarioId": cuenta_id,
        "rolAnterior": "productor",
        "rolNuevo": "productor",
    }
    assert len(_eventos("rol_asignado")) == 1


def test_consultar_permisos_de_productor(client: TestClient, email_gateway) -> None:
    cuenta_id = crear_cuenta_verificada(client, email_gateway)
    asignacion = client.post(
        f"{ADMIN_ROLES_URL}/{cuenta_id}/roles", json={"rol": "productor"}
    )
    assert asignacion.status_code == 200

    respuesta = client.get(PERMISSIONS_URL, headers=_headers_sesion(client))

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["success"] is True
    assert cuerpo["message"] == "Permisos consultados correctamente."
    assert set(cuerpo["data"]) == CAMPOS_PERMISOS
    datos = cuerpo["data"]
    assert datos["usuarioId"] == cuenta_id
    assert datos["rol"] == "productor"
    assert {
        "catalog.product.create",
        "catalog.product.edit",
        "commerce.sales.read",
    } <= set(datos["permisos"])
    assert "catalog.product" in datos["recursos"]


def test_consultar_permisos_sin_token_devuelve_401(client: TestClient) -> None:
    respuesta = client.get(PERMISSIONS_URL)

    assert respuesta.status_code == 401
    assert respuesta.json()["data"]["codigo"] == "credenciales_invalidas"


def test_scopes_del_token_reflejan_el_rol_vigente(
    client: TestClient, email_gateway, service: AuthService
) -> None:
    cuenta_id = crear_cuenta_verificada(client, email_gateway)
    asignacion = client.post(
        f"{ADMIN_ROLES_URL}/{cuenta_id}/roles", json={"rol": "productor"}
    )
    assert asignacion.status_code == 200

    token = iniciar_sesion(client).json()["data"]["accessToken"]
    claims = service.session_token_manager.decode_access_token(token, verify_exp=False)

    assert claims["rol"] == "productor"
    assert "catalog.product.create" in claims["scopes"]


def test_validador_interno_permite_a_administrador(client: TestClient) -> None:
    service = RolesPermissionsService(
        repo=auth_repository,
        settings=client.app.state.settings,
        clock=lambda: datetime.now(timezone.utc),
    )
    admin = Actor(id="usr_admin", roles=(Role.ADMINISTRADOR.value,))

    service.ensure_permiso(
        permiso="admin.users.roles.write",
        actor=admin,
        recurso="admin.users",
        accion="write",
    )

    assert not _eventos("permiso_denegado")


def test_validador_interno_deniega_y_audita_a_consumidor(
    client: TestClient, email_gateway
) -> None:
    cuenta_id = crear_cuenta_verificada(client, email_gateway)
    cuenta = auth_repository.obtener_cuenta_por_id(cuenta_id)
    service = RolesPermissionsService(
        repo=auth_repository,
        settings=client.app.state.settings,
        clock=lambda: datetime.now(timezone.utc),
    )

    with pytest.raises(PermissionDeniedError):
        service.ensure_permiso(
            permiso="admin.users.roles.write",
            cuenta=cuenta,
            recurso="admin.users",
            accion="write",
            ip="127.0.0.1",
        )

    denegacion = _eventos("permiso_denegado")[0]
    assert denegacion.cuenta_id == cuenta_id
    assert denegacion.metadata["permiso"] == "admin.users.roles.write"
    assert denegacion.metadata["recurso"] == "admin.users"
