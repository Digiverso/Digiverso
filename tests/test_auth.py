from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app.domain.auth import AccountStatus
from app.repository.auth_repository import auth_repository
from app.repository.email_repository import render_verification_template
from app.services.auth_service import AuthService
from tests.conftest import PASSWORD, extraer_token, payload_registro


def test_registro_exitoso_crea_cuenta_pendiente_y_envia_correo(
    client: TestClient,
    email_gateway,
) -> None:
    respuesta = client.post("/api/v1/auth/register", json=payload_registro())

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["message"] == "Cuenta creada. Revisa tu correo para verificarla."
    assert cuerpo["success"] is True
    assert cuerpo["data"]["userId"] == "usr_001"
    assert cuerpo["data"]["correo"] == "ana@example.com"
    assert cuerpo["data"]["estado"] == "pendiente_verificacion"
    assert cuerpo["data"]["rol"] == "consumidor"
    assert "password" not in cuerpo["data"]

    cuenta = auth_repository.obtener_cuenta_por_correo("ana@example.com")
    assert cuenta is not None
    assert cuenta.estado is AccountStatus.PENDIENTE
    assert cuenta.password_hash != PASSWORD
    assert len(email_gateway.sent) == 1

    audit_text = str(auth_repository.eventos_auditoria())
    tipos = [evento.tipo for evento in auth_repository.eventos_auditoria()]
    assert "registro_creado" in tipos
    assert "correo_verificacion_enviado" in tipos
    assert PASSWORD not in audit_text
    assert extraer_token(email_gateway) not in audit_text
    assert "ana@example.com" not in audit_text


def test_correo_duplicado_responde_409_y_no_crea_otra_cuenta(client: TestClient) -> None:
    primera = client.post("/api/v1/auth/register", json=payload_registro())
    segunda = client.post("/api/v1/auth/register", json=payload_registro())

    assert primera.status_code == 201
    assert segunda.status_code == 409
    assert segunda.json()["success"] is False
    assert segunda.json()["data"]["codigo"] == "correo_duplicado"
    assert auth_repository.total_cuentas() == 1


def test_contrasena_debil_responde_400_con_detalle(client: TestClient) -> None:
    respuesta = client.post(
        "/api/v1/auth/register",
        json=payload_registro(password="abc"),
    )

    assert respuesta.status_code == 400
    cuerpo = respuesta.json()
    assert cuerpo["success"] is False
    assert cuerpo["data"]["codigo"] == "politica_contrasena"
    assert any("al menos 8 caracteres" in detalle for detalle in cuerpo["data"]["detalle"])
    assert any("mayúscula" in detalle for detalle in cuerpo["data"]["detalle"])
    assert auth_repository.total_cuentas() == 0


def test_token_expirado_responde_410_y_no_activa_la_cuenta(
    client: TestClient,
    email_gateway,
    clock,
) -> None:
    registro = client.post("/api/v1/auth/register", json=payload_registro())
    assert registro.status_code == 201
    token = extraer_token(email_gateway)

    clock["now"] = clock["now"] + timedelta(minutes=16)
    verificacion = client.post("/api/v1/auth/email/verify", json={"token": token})

    assert verificacion.status_code == 410
    assert verificacion.json()["success"] is False
    assert verificacion.json()["data"]["codigo"] == "token_invalido"
    cuenta = auth_repository.obtener_cuenta_por_correo("ana@example.com")
    assert cuenta is not None
    assert cuenta.estado is AccountStatus.PENDIENTE


def test_verificacion_exitosa_activa_cuenta_y_habilita_login(
    client: TestClient,
    email_gateway,
) -> None:
    registro = client.post("/api/v1/auth/register", json=payload_registro())
    token = extraer_token(email_gateway)

    verificacion = client.post("/api/v1/auth/email/verify", json={"token": token})

    assert verificacion.status_code == 200
    cuerpo = verificacion.json()
    assert cuerpo["message"] == "Cuenta verificada correctamente."
    assert cuerpo["data"]["cuentaId"] == registro.json()["data"]["userId"]
    assert cuerpo["data"]["estado"] == "activa"
    assert cuerpo["data"]["fechaVerificacion"] is not None

    login = client.post(
        "/api/v1/auth/login",
        json={"correo": "ana@example.com", "password": PASSWORD},
    )
    assert login.status_code == 200
    assert login.json()["data"]["estado"] == "activa"

    desconocido = client.post(
        "/api/v1/auth/login",
        json={"correo": "otra@example.com", "password": PASSWORD},
    )
    assert desconocido.status_code == 401
    assert desconocido.json()["message"] == "Correo o contraseña inválidos."


def test_token_reutilizado_responde_410(client: TestClient, email_gateway) -> None:
    client.post("/api/v1/auth/register", json=payload_registro())
    token = extraer_token(email_gateway)

    primera = client.post("/api/v1/auth/email/verify", json={"token": token})
    segunda = client.post("/api/v1/auth/email/verify", json={"token": token})

    assert primera.status_code == 200
    assert segunda.status_code == 410
    cuenta = auth_repository.obtener_cuenta_por_correo("ana@example.com")
    assert cuenta is not None
    assert cuenta.estado is AccountStatus.ACTIVA
    assert cuenta.verificado_en is not None


def test_login_bloqueado_mientras_la_cuenta_esta_pendiente(client: TestClient) -> None:
    client.post("/api/v1/auth/register", json=payload_registro())

    login = client.post(
        "/api/v1/auth/login",
        json={"correo": "ana@example.com", "password": PASSWORD},
    )

    assert login.status_code == 403
    assert login.json()["data"]["codigo"] == "cuenta_no_verificada"


def test_aceptacion_de_politicas_es_obligatoria(client: TestClient) -> None:
    respuesta = client.post(
        "/api/v1/auth/register",
        json=payload_registro(aceptar_politicas=False),
    )

    assert respuesta.status_code == 400
    assert any(
        error["campo"] == "aceptar_politicas"
        for error in respuesta.json()["data"]["detalle"]
    )


def test_registro_aplica_rate_limit(client: TestClient, service: AuthService) -> None:
    from app.core.rate_limit import RateLimiter

    service.rate_limiter = RateLimiter(limit=1, window_seconds=60)

    primera = client.post("/api/v1/auth/register", json=payload_registro())
    segunda = client.post(
        "/api/v1/auth/register",
        json=payload_registro(correo="otra@example.com"),
    )

    assert primera.status_code == 201
    assert segunda.status_code == 429
    assert segunda.json()["data"]["codigo"] == "limite_excedido"


def test_plantilla_de_correo_incluye_enlace_y_vigencia() -> None:
    html = render_verification_template("Ana", "http://localhost/verificar?token=abc", 15)

    assert "Verifica tu cuenta de Digiverso" in html
    assert "http://localhost/verificar?token=abc" in html
    assert "15 minutos" in html


def test_openapi_documenta_los_endpoints(client: TestClient) -> None:
    esquema = client.get("/openapi.json").json()

    assert "/api/v1/auth/register" in esquema["paths"]
    assert "/api/v1/auth/email/verify" in esquema["paths"]
    assert esquema["paths"]["/api/v1/auth/register"]["post"]["responses"]["201"]


def test_swagger_ui_y_ejemplos_estan_disponibles(client: TestClient) -> None:
    docs = client.get("/docs")
    esquema = client.get("/openapi.json").json()

    assert docs.status_code == 200
    assert "swagger-ui" in docs.text.lower()
    assert "example" in esquema["components"]["schemas"]["RegisterRequest"]
    assert "example" in esquema["components"]["schemas"]["VerifyRequest"]
