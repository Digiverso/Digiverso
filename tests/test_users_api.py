from __future__ import annotations

import base64
from datetime import timedelta

from fastapi.testclient import TestClient

from app.domain.auth import AccountStatus, Role
from app.repository.auth_repository import auth_repository
from tests.conftest import PASSWORD
from tests.test_auth_session import crear_cuenta_verificada, iniciar_sesion

USERS_URL = "/api/v1/users"
CAMPOS_PERFIL = {
    "id",
    "nombre",
    "correo",
    "rol",
    "biografia",
    "foto",
    "fechaRegistro",
}


def _headers_autenticados(client: TestClient, email_gateway) -> dict[str, str]:
    crear_cuenta_verificada(client, email_gateway)
    token = iniciar_sesion(client).json()["data"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def test_get_me_devuelve_solo_el_perfil_propio(client: TestClient, email_gateway) -> None:
    headers = _headers_autenticados(client, email_gateway)

    respuesta = client.get(f"{USERS_URL}/me", headers=headers)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["success"] is True
    assert cuerpo["message"] == "Perfil consultado correctamente."
    assert set(cuerpo["data"]) == CAMPOS_PERFIL
    assert cuerpo["data"]["id"] == "usr_001"
    assert cuerpo["data"]["nombre"] == "Ana Pérez"
    assert cuerpo["data"]["correo"] == "ana@example.com"
    assert cuerpo["data"]["rol"] == Role.CONSUMIDOR.value
    assert cuerpo["data"]["biografia"] is None
    assert cuerpo["data"]["foto"] is None
    assert cuerpo["data"]["fechaRegistro"]
    assert "password" not in str(cuerpo["data"]).lower()
    assert "token" not in str(cuerpo["data"]).lower()


def test_patch_me_actualiza_y_audita_campos_modificados(
    client: TestClient,
    email_gateway,
) -> None:
    headers = _headers_autenticados(client, email_gateway)

    respuesta = client.patch(
        f"{USERS_URL}/me",
        json={"nombre": "Ana Torres", "biografia": "Ilustradora digital."},
        headers=headers,
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["message"] == "Perfil actualizado correctamente."
    assert cuerpo["data"]["nombre"] == "Ana Torres"
    assert cuerpo["data"]["biografia"] == "Ilustradora digital."
    assert set(cuerpo["data"]) == CAMPOS_PERFIL
    assert client.get(f"{USERS_URL}/me", headers=headers).json()["data"] == cuerpo["data"]

    eventos = [
        evento
        for evento in auth_repository.eventos_auditoria()
        if evento.tipo == "perfil_actualizado"
    ]
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento.cuenta_id == "usr_001"
    assert evento.ip
    assert evento.registrado_en is not None
    assert evento.metadata["usuario"] == "usr_001"
    assert evento.metadata["fecha"]
    assert evento.metadata["campos"] == ["nombre", "biografia"]
    assert evento.metadata["antes"]["nombre"] == "Ana Pérez"
    assert evento.metadata["despues"]["nombre"] == "Ana Torres"
    assert "password" not in str(evento.metadata).lower()
    assert "token" not in str(evento.metadata).lower()


def test_foto_demasiado_grande_devuelve_400_y_no_modifica(
    client: TestClient,
    email_gateway,
) -> None:
    headers = _headers_autenticados(client, email_gateway)
    maximo = client.app.state.settings.profile_photo_max_bytes
    contenido = b"\xff\xd8\xff" + b"\x00" * maximo

    respuesta = client.patch(
        f"{USERS_URL}/me",
        files={"foto": ("foto.png", contenido, "image/png")},
        headers=headers,
    )

    assert respuesta.status_code == 400
    cuerpo = respuesta.json()
    assert cuerpo["success"] is False
    assert cuerpo["data"]["campo"] == "foto"
    assert cuerpo["data"]["detalle"]["maximo"] == maximo
    assert auth_repository.obtener_cuenta_por_id("usr_001").foto is None
    assert not [
        evento
        for evento in auth_repository.eventos_auditoria()
        if evento.tipo == "perfil_actualizado"
    ]


def test_foto_valida_se_guarda_y_devuelve_url_cdn(
    client: TestClient,
    email_gateway,
) -> None:
    headers = _headers_autenticados(client, email_gateway)
    contenido = b"\x89PNG\r\n\x1a\n" + b"contenido-png"
    data_url = "data:image/png;base64," + base64.b64encode(contenido).decode("ascii")

    respuesta = client.patch(
        f"{USERS_URL}/me",
        json={"foto": data_url},
        headers=headers,
    )

    assert respuesta.status_code == 200
    url = respuesta.json()["data"]["foto"]
    assert url.startswith("https://cdn.digiverso.com/users/usr_001/foto-")
    assert url.endswith(".png")

    clave = url.removeprefix("https://cdn.digiverso.com/")
    assert (client.app.state.photo_storage.base_path / clave).read_bytes() == contenido


def test_foto_con_contenido_que_no_es_imagen_se_rechaza(
    client: TestClient,
    email_gateway,
) -> None:
    headers = _headers_autenticados(client, email_gateway)
    data_url = "data:image/png;base64," + base64.b64encode(b"texto plano").decode("ascii")

    respuesta = client.patch(f"{USERS_URL}/me", json={"foto": data_url}, headers=headers)

    assert respuesta.status_code == 400
    assert respuesta.json()["data"]["campo"] == "foto"
    assert auth_repository.obtener_cuenta_por_id("usr_001").foto is None


def test_campos_protegidos_no_son_editables(client: TestClient, email_gateway) -> None:
    headers = _headers_autenticados(client, email_gateway)
    intentos = [
        ("rol", "admin"),
        ("correo", "otro@example.com"),
        ("estado", "activa"),
        ("id", "usr_002"),
        ("userId", "usr_002"),
    ]

    for campo, valor in intentos:
        respuesta = client.patch(f"{USERS_URL}/me", json={campo: valor}, headers=headers)
        assert respuesta.status_code == 400
        assert respuesta.json()["data"]["campo"] == campo

    cuenta = auth_repository.obtener_cuenta_por_id("usr_001")
    assert cuenta.rol is Role.CONSUMIDOR
    assert cuenta.correo == "ana@example.com"
    assert cuenta.estado is AccountStatus.ACTIVA
    assert not [
        evento
        for evento in auth_repository.eventos_auditoria()
        if evento.tipo == "perfil_actualizado"
    ]


def test_no_se_puede_acceder_a_un_perfil_ajeno(client: TestClient, email_gateway) -> None:
    headers = _headers_autenticados(client, email_gateway)

    consulta = client.get(f"{USERS_URL}/usr_002", headers=headers)
    edicion = client.patch(
        f"{USERS_URL}/usr_002",
        json={"nombre": "Intruso"},
        headers=headers,
    )
    con_id = client.patch(
        f"{USERS_URL}/me",
        json={"id": "usr_002", "nombre": "Intruso"},
        headers=headers,
    )

    assert consulta.status_code == 404
    assert consulta.json()["success"] is False
    assert edicion.status_code == 404
    assert con_id.status_code == 400
    assert con_id.json()["data"]["campo"] == "id"
    assert auth_repository.obtener_cuenta_por_id("usr_001").nombre == "Ana Pérez"


def test_token_requerido_y_sesion_revocada_no_autorizan(
    client: TestClient,
    email_gateway,
) -> None:
    crear_cuenta_verificada(client, email_gateway)
    login = iniciar_sesion(client)
    headers = {"Authorization": f"Bearer {login.json()['data']['accessToken']}"}

    assert client.get(f"{USERS_URL}/me").status_code == 401
    assert (
        client.get(
            f"{USERS_URL}/me",
            headers={"Authorization": "Bearer token_invalido"},
        ).status_code
        == 401
    )

    cliente = client.post(
        "/api/v1/auth/logout",
        json={"refreshToken": login.json()["data"]["refreshToken"]},
    )
    assert cliente.status_code == 204
    assert client.get(f"{USERS_URL}/me", headers=headers).status_code == 401


def test_token_expirado_no_autoriza(client: TestClient, email_gateway, clock) -> None:
    headers = _headers_autenticados(client, email_gateway)

    clock["now"] = clock["now"] + timedelta(minutes=16)

    assert client.patch(
        f"{USERS_URL}/me",
        json={"nombre": "Fuera de tiempo"},
        headers=headers,
    ).status_code == 401
    assert auth_repository.obtener_cuenta_por_id("usr_001").nombre == "Ana Pérez"


def test_openapi_documenta_los_endpoints_de_perfil(client: TestClient) -> None:
    esquema = client.get("/openapi.json").json()
    rutas = esquema["paths"]
    propiedades = esquema["components"]["schemas"]["UserProfile"]["properties"]

    assert "/api/v1/users/me" in rutas
    assert "get" in rutas["/api/v1/users/me"]
    assert "patch" in rutas["/api/v1/users/me"]
    assert set(propiedades) == CAMPOS_PERFIL
    assert any(tag["name"] == "Usuarios" for tag in esquema["tags"])
    assert "multipart/form-data" in rutas["/api/v1/users/me"]["patch"]["requestBody"]["content"]


def test_contraseña_no_aparece_en_la_respuesta_de_perfil(
    client: TestClient,
    email_gateway,
) -> None:
    headers = _headers_autenticados(client, email_gateway)

    texto = client.get(f"{USERS_URL}/me", headers=headers).text

    assert PASSWORD not in texto
