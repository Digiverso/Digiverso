from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app.repository.auth_repository import auth_repository
from app.repository.email_repository import render_password_reset_template
from app.services.auth_service import AuthService
from tests.conftest import PASSWORD, extraer_token, extraer_token_recuperacion, payload_registro

CORREO = "ana@example.com"
NUEVA_PASSWORD = "NuevaClave1!"


def crear_cuenta_verificada(client: TestClient, email_gateway) -> str:
    registro = client.post("/api/v1/auth/register", json=payload_registro())
    token = extraer_token(email_gateway)
    client.post("/api/v1/auth/email/verify", json={"token": token})
    return registro.json()["data"]["userId"]


def iniciar_sesion(client: TestClient, password: str = PASSWORD):
    return client.post(
        "/api/v1/auth/login",
        json={"correo": CORREO, "password": password},
    )


def test_login_emite_tokens_rs256_y_expiracion(
    client: TestClient,
    email_gateway,
    service: AuthService,
    clock,
) -> None:
    crear_cuenta_verificada(client, email_gateway)

    respuesta = iniciar_sesion(client)

    assert respuesta.status_code == 200
    datos = respuesta.json()["data"]
    assert datos["refreshToken"].startswith("rt_")
    assert datos["expiraEn"] == 900
    assert datos["usuario"] == {"id": "usr_001", "rol": "consumidor"}

    claims = service.session_token_manager.decode_access_token(
        datos["accessToken"],
        verify_exp=False,
    )
    assert claims["sub"] == "usr_001"
    assert claims["rol"] == "consumidor"
    assert claims["iss"] == "digiverso"
    assert claims["aud"] == "digiverso-api"
    assert claims["exp"] - claims["iat"] == 900

    sesiones = auth_repository.sesiones_activas("usr_001", clock["now"])
    assert len(sesiones) == 1

    audit_text = str(auth_repository.eventos_auditoria())
    tipos = [evento.tipo for evento in auth_repository.eventos_auditoria()]
    assert "login_exitoso" in tipos
    assert datos["accessToken"] not in audit_text
    assert datos["refreshToken"] not in audit_text


def test_bloqueo_transitorio_por_intentos_fallidos(client: TestClient, email_gateway) -> None:
    crear_cuenta_verificada(client, email_gateway)

    respuestas = [iniciar_sesion(client, "Incorrecta1!") for _ in range(5)]

    assert [respuesta.status_code for respuesta in respuestas] == [401, 401, 401, 401, 423]
    bloqueo = respuestas[-1].json()
    assert bloqueo["data"]["codigo"] == "cuenta_bloqueada"
    assert bloqueo["data"]["reintentosEnSegundos"] == 900

    posterior = iniciar_sesion(client)
    assert posterior.status_code == 423

    tipos = [evento.tipo for evento in auth_repository.eventos_auditoria()]
    assert "cuenta_bloqueada" in tipos
    assert "login_bloqueado" in tipos


def test_cuenta_se_desbloquea_despues_de_la_vigencia(
    client: TestClient,
    email_gateway,
    clock,
) -> None:
    crear_cuenta_verificada(client, email_gateway)
    for _ in range(5):
        iniciar_sesion(client, "Incorrecta1!")

    clock["now"] = clock["now"] + timedelta(minutes=16)
    respuesta = iniciar_sesion(client)

    assert respuesta.status_code == 200
    cuenta = auth_repository.obtener_cuenta_por_correo(CORREO)
    assert cuenta is not None
    assert cuenta.bloqueado_hasta is None
    assert cuenta.intentos_fallidos == 0


def test_logout_revoca_el_refresh_token(client: TestClient, email_gateway, clock) -> None:
    crear_cuenta_verificada(client, email_gateway)
    login = iniciar_sesion(client)
    refresh_token = login.json()["data"]["refreshToken"]

    logout = client.post("/api/v1/auth/logout", json={"refreshToken": refresh_token})

    assert logout.status_code == 204
    assert logout.content == b""
    assert client.post("/api/v1/auth/logout", json={"refreshToken": refresh_token}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refreshToken": refresh_token}).status_code == 401
    assert auth_repository.sesiones_activas("usr_001", clock["now"]) == []


def test_refresh_rota_el_token_y_emite_otra_sesion(
    client: TestClient,
    email_gateway,
    clock,
) -> None:
    crear_cuenta_verificada(client, email_gateway)
    login = iniciar_sesion(client)
    refresh_anterior = login.json()["data"]["refreshToken"]

    renovacion = client.post("/api/v1/auth/refresh", json={"refreshToken": refresh_anterior})

    assert renovacion.status_code == 200
    refresh_nuevo = renovacion.json()["data"]["refreshToken"]
    assert refresh_nuevo != refresh_anterior
    assert client.post("/api/v1/auth/refresh", json={"refreshToken": refresh_anterior}).status_code == 401
    assert len(auth_repository.sesiones_activas("usr_001", clock["now"])) == 1
    assert client.post("/api/v1/auth/logout", json={"refreshToken": refresh_nuevo}).status_code == 204


def test_recuperacion_con_correo_inexistente_es_generica(
    client: TestClient,
    email_gateway,
) -> None:
    inexistente = client.post(
        "/api/v1/auth/password/forgot",
        json={"correo": "noexiste@example.com"},
    )

    crear_cuenta_verificada(client, email_gateway)
    existente = client.post(
        "/api/v1/auth/password/forgot",
        json={"correo": CORREO},
    )

    assert inexistente.status_code == 200
    assert existente.status_code == 200
    assert inexistente.json() == existente.json()
    assert len(email_gateway.password_resets) == 1

    eventos = [evento for evento in auth_repository.eventos_auditoria() if evento.tipo == "recuperacion_solicitada"]
    assert len(eventos) == 2
    assert any(evento.cuenta_id is None for evento in eventos)


def test_token_de_recuperacion_expirado_no_cambia_la_contrasena(
    client: TestClient,
    email_gateway,
    clock,
) -> None:
    crear_cuenta_verificada(client, email_gateway)
    cuenta = auth_repository.obtener_cuenta_por_correo(CORREO)
    assert cuenta is not None
    hash_original = cuenta.password_hash

    client.post("/api/v1/auth/password/forgot", json={"correo": CORREO})
    token = extraer_token_recuperacion(email_gateway)
    clock["now"] = clock["now"] + timedelta(minutes=31)

    respuesta = client.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "nuevaPassword": NUEVA_PASSWORD},
    )

    assert respuesta.status_code == 410
    assert respuesta.json()["data"]["codigo"] == "token_recuperacion_invalido"
    assert cuenta.password_hash == hash_original
    assert iniciar_sesion(client).status_code == 200


def test_reset_exitoso_actualiza_contrasena_y_revoca_sesiones(
    client: TestClient,
    email_gateway,
    clock,
) -> None:
    crear_cuenta_verificada(client, email_gateway)
    iniciar_sesion(client)
    assert len(auth_repository.sesiones_activas("usr_001", clock["now"])) == 1

    client.post("/api/v1/auth/password/forgot", json={"correo": CORREO})
    token = extraer_token_recuperacion(email_gateway)

    respuesta = client.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "nuevaPassword": NUEVA_PASSWORD},
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["message"] == "Contraseña actualizada correctamente."
    assert auth_repository.sesiones_activas("usr_001", clock["now"]) == []
    assert iniciar_sesion(client, PASSWORD).status_code == 401
    assert iniciar_sesion(client, NUEVA_PASSWORD).status_code == 200
    assert client.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "nuevaPassword": "OtraClave2!"},
    ).status_code == 410

    audit_text = str(auth_repository.eventos_auditoria())
    tipos = [evento.tipo for evento in auth_repository.eventos_auditoria()]
    assert "contrasena_restablecida" in tipos
    assert token not in audit_text
    assert NUEVA_PASSWORD not in audit_text


def test_reset_con_contrasena_debil_no_consume_el_token(client: TestClient, email_gateway) -> None:
    crear_cuenta_verificada(client, email_gateway)
    client.post("/api/v1/auth/password/forgot", json={"correo": CORREO})
    token = extraer_token_recuperacion(email_gateway)

    debil = client.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "nuevaPassword": "abc"},
    )

    assert debil.status_code == 400
    assert debil.json()["data"]["codigo"] == "politica_contrasena"

    correcta = client.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "nuevaPassword": NUEVA_PASSWORD},
    )
    assert correcta.status_code == 200


def test_plantilla_de_recuperacion_incluye_enlace_y_vigencia() -> None:
    html = render_password_reset_template("Ana", "http://localhost/reset?token=abc", 30)

    assert "Restablece tu contraseña de Digiverso" in html
    assert "http://localhost/reset?token=abc" in html
    assert "30 minutos" in html


def test_openapi_documenta_los_endpoints_hu02(client: TestClient) -> None:
    esquema = client.get("/openapi.json").json()
    paths = esquema["paths"]

    assert "/api/v1/auth/logout" in paths
    assert "/api/v1/auth/refresh" in paths
    assert "/api/v1/auth/password/forgot" in paths
    assert "/api/v1/auth/password/reset" in paths
    assert "accessToken" in esquema["components"]["schemas"]["LoginResponseData"]["properties"]
