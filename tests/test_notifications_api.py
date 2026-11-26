from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.repository.email_repository import EmailDelivery
from app.repository.notifications import notification_repository
from app.services.notifications import NotificationService
from tests.conftest import PASSWORD, extraer_token, payload_registro

BASE = "/api/v1/users/me"
PREFERENCES_URL = f"{BASE}/notification-preferences"
NOTIFICATIONS_URL = f"{BASE}/notifications"


class FakeNotificationSender:
    def __init__(self, *, fallos: int = 0) -> None:
        self.enviados: list[dict[str, str]] = []
        self.fallos = fallos

    def send(
        self, correo: str, nombre: str, asunto: str, mensaje: str
    ) -> EmailDelivery:
        self.enviados.append(
            {"correo": correo, "nombre": nombre, "asunto": asunto, "mensaje": mensaje}
        )
        if len(self.enviados) <= self.fallos:
            raise RuntimeError("smtp temporalmente caído")
        return EmailDelivery(
            provider="fake",
            message_id="fake_ntf_1",
            estado="enviado",
            intento_en=datetime.now(timezone.utc),
        )


@pytest.fixture(autouse=True)
def _reset_notificaciones() -> Any:
    notification_repository.reset()
    yield
    notification_repository.reset()


def crear_cuenta_verificada_correo(
    client: TestClient, email_gateway, correo: str
) -> str:
    registro = client.post(
        "/api/v1/auth/register", json=payload_registro(correo=correo)
    )
    token = extraer_token(email_gateway)
    client.post("/api/v1/auth/email/verify", json={"token": token})
    return registro.json()["data"]["userId"]


def headers_de(client: TestClient, correo: str = "ana@example.com") -> dict[str, str]:
    respuesta = client.post(
        "/api/v1/auth/login", json={"correo": correo, "password": PASSWORD}
    )
    token = respuesta.json()["data"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def servicio_de(
    client: TestClient, clock, sender: FakeNotificationSender | None = None
) -> NotificationService:
    return NotificationService(
        repo=notification_repository,
        settings=client.app.state.settings,
        clock=lambda: clock["now"],
        sender=sender,
    )


def test_preferencias_validas_se_guardan(client: TestClient, email_gateway) -> None:
    crear_cuenta_verificada_correo(client, email_gateway, "ana@example.com")

    respuesta = client.put(
        PREFERENCES_URL,
        json={
            "canales": ["in_app", "email"],
            "tipos": ["cuenta_verificada", "password_reset"],
        },
        headers=headers_de(client),
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["message"] == "Preferencias de notificación actualizadas."
    assert cuerpo["data"] == {
        "canales": ["in_app", "email"],
        "tipos": ["cuenta_verificada", "password_reset"],
    }
    guardadas = notification_repository.obtener_preferencias("usr_001")
    assert guardadas is not None
    assert [canal.value for canal in guardadas.canales] == ["in_app", "email"]


def test_canal_no_permitido_devuelve_400_sin_cambios(
    client: TestClient, email_gateway
) -> None:
    crear_cuenta_verificada_correo(client, email_gateway, "ana@example.com")

    respuesta = client.put(
        PREFERENCES_URL,
        json={"canales": ["sms"], "tipos": ["cuenta_verificada"]},
        headers=headers_de(client),
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["data"]["codigo"] == "canal_no_permitido"
    assert notification_repository.obtener_preferencias("usr_001") is None


def test_tipo_no_permitido_devuelve_400_sin_cambios(
    client: TestClient, email_gateway
) -> None:
    crear_cuenta_verificada_correo(client, email_gateway, "ana@example.com")

    respuesta = client.put(
        PREFERENCES_URL,
        json={"canales": ["in_app"], "tipos": ["evento_desconocido"]},
        headers=headers_de(client),
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["data"]["codigo"] == "tipo_no_permitido"
    assert notification_repository.obtener_preferencias("usr_001") is None


def test_bandeja_es_propia_pagina_y_ordena_descendente(
    client: TestClient, email_gateway, clock
) -> None:
    ana = crear_cuenta_verificada_correo(client, email_gateway, "ana@example.com")
    bob = crear_cuenta_verificada_correo(client, email_gateway, "bob@example.com")
    servicio = servicio_de(client, clock)
    servicio.notificar_evento(cuenta_id=ana, tipo="cuenta_verificada")
    clock["now"] = clock["now"] + timedelta(minutes=1)
    servicio.notificar_evento(cuenta_id=ana, tipo="perfil_actualizado")
    servicio.notificar_evento(cuenta_id=bob, tipo="cuenta_verificada")

    respuesta = client.get(
        NOTIFICATIONS_URL,
        params={"pagina": 1, "tamano": 1},
        headers=headers_de(client),
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["message"] == "Notificaciones consultadas correctamente."
    assert cuerpo["data"]["pagina"] == 1
    assert cuerpo["data"]["total"] == 2
    assert len(cuerpo["data"]["items"]) == 1
    item = cuerpo["data"]["items"][0]
    assert set(item) == {"id", "tipo", "mensaje", "canal", "leida", "fecha"}
    assert item["tipo"] == "perfil_actualizado"
    assert item["leida"] is False

    segunda = client.get(
        NOTIFICATIONS_URL,
        params={"pagina": 2, "tamano": 1},
        headers=headers_de(client),
    )
    assert segunda.json()["data"]["items"][0]["tipo"] == "cuenta_verificada"


def test_marcar_leida_es_idempotente(
    client: TestClient, email_gateway, clock
) -> None:
    cuenta_id = crear_cuenta_verificada_correo(client, email_gateway, "ana@example.com")
    notificacion = servicio_de(client, clock).notificar_evento(
        cuenta_id=cuenta_id, tipo="cuenta_verificada"
    )
    assert notificacion is not None

    primera = client.patch(
        f"{NOTIFICATIONS_URL}/{notificacion.id}/read", headers=headers_de(client)
    )
    segunda = client.patch(
        f"{NOTIFICATIONS_URL}/{notificacion.id}/read", headers=headers_de(client)
    )

    assert primera.status_code == segunda.status_code == 200
    assert primera.json()["data"] == {"id": notificacion.id, "leida": True}
    assert segunda.json()["data"] == {"id": notificacion.id, "leida": True}
    assert notification_repository.obtener_por_id(notificacion.id).leida is True


def test_notificacion_ajena_responde_404_sin_modificar(
    client: TestClient, email_gateway, clock
) -> None:
    crear_cuenta_verificada_correo(client, email_gateway, "ana@example.com")
    crear_cuenta_verificada_correo(client, email_gateway, "bob@example.com")
    ajena = servicio_de(client, clock).notificar_evento(
        cuenta_id="usr_002", tipo="cuenta_verificada"
    )
    assert ajena is not None

    respuesta = client.patch(
        f"{NOTIFICATIONS_URL}/{ajena.id}/read", headers=headers_de(client)
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["data"]["codigo"] == "notificacion_no_encontrada"
    assert notification_repository.obtener_por_id(ajena.id).leida is False


def test_notificacion_critica_no_se_silencia(
    client: TestClient, email_gateway, clock
) -> None:
    cuenta_id = crear_cuenta_verificada_correo(client, email_gateway, "ana@example.com")
    cabeceras = headers_de(client)
    preferencias = client.put(
        PREFERENCES_URL,
        json={"canales": ["in_app"], "tipos": []},
        headers=cabeceras,
    )
    assert preferencias.status_code == 200

    sender = FakeNotificationSender()
    notificacion = servicio_de(client, clock, sender).notificar_evento(
        cuenta_id=cuenta_id,
        tipo="password_reset",
        nombre="Ana Pérez",
        correo="ana@example.com",
    )

    assert notificacion is not None
    assert len(sender.enviados) == 1
    entregas = notification_repository.entregas_de(notificacion.id)
    assert {entrega.canal.value for entrega in entregas} == {"email", "in_app"}
    assert all(entrega.estado == "enviado" for entrega in entregas)


def test_notificacion_no_critica_silenciada_por_tipo(
    client: TestClient, email_gateway, clock
) -> None:
    cuenta_id = crear_cuenta_verificada_correo(client, email_gateway, "ana@example.com")
    cabeceras = headers_de(client)
    respuesta = client.put(
        PREFERENCES_URL,
        json={"canales": ["email"], "tipos": []},
        headers=cabeceras,
    )
    assert respuesta.status_code == 200

    notificacion = servicio_de(client, clock, FakeNotificationSender()).notificar_evento(
        cuenta_id=cuenta_id, tipo="cuenta_verificada"
    )

    assert notificacion is None
    bandeja = client.get(NOTIFICATIONS_URL, headers=cabeceras)
    assert bandeja.status_code == 200
    assert bandeja.json()["data"]["total"] == 0


def tipo_cuenta(cuenta_id: str) -> Any:
    """Devuelve un ``Account`` mínimo para consultar la bandeja en pruebas."""

    from app.domain.auth import Account, AccountStatus, Role

    return Account(
        id=cuenta_id,
        nombre="Ana Pérez",
        correo="ana@example.com",
        password_hash="",
        estado=AccountStatus.ACTIVA,
        rol=Role.CONSUMIDOR,
    )


def test_idempotencia_por_clave_no_duplica(
    client: TestClient, email_gateway, clock
) -> None:
    cuenta_id = crear_cuenta_verificada_correo(client, email_gateway, "ana@example.com")
    servicio = servicio_de(client, clock, FakeNotificationSender())

    primera = servicio.notificar_evento(
        cuenta_id=cuenta_id,
        tipo="cuenta_verificada",
        clave_idempotencia="verificacion:usr_001",
    )
    segunda = servicio.notificar_evento(
        cuenta_id=cuenta_id,
        tipo="cuenta_verificada",
        clave_idempotencia="verificacion:usr_001",
    )

    assert primera is not None and segunda is not None
    assert primera.id == segunda.id
    _, total = servicio_de(client, clock).bandeja(tipo_cuenta(cuenta_id))
    assert total == 1


def test_retencion_aut_11_elimina_antiguas(
    client: TestClient, email_gateway, clock
) -> None:
    cuenta_id = crear_cuenta_verificada_correo(client, email_gateway, "ana@example.com")
    servicio = servicio_de(client, clock)
    servicio.notificar_evento(cuenta_id=cuenta_id, tipo="cuenta_verificada")

    dias = client.app.state.settings.notification_retention_days
    clock["now"] = clock["now"] + timedelta(days=dias + 1)

    respuesta = client.get(NOTIFICATIONS_URL, headers=headers_de(client))

    assert respuesta.status_code == 200
    assert respuesta.json()["data"] == {"items": [], "pagina": 1, "total": 0}


def test_reintentos_de_entrega_no_duplican_notificacion(
    client: TestClient, email_gateway, clock
) -> None:
    cuenta_id = crear_cuenta_verificada_correo(client, email_gateway, "ana@example.com")
    sender = FakeNotificationSender(fallos=99)
    servicio = servicio_de(client, clock, sender)

    notificacion = servicio.notificar_evento(
        cuenta_id=cuenta_id,
        tipo="cuenta_verificada",
        nombre="Ana Pérez",
        correo="ana@example.com",
    )

    assert notificacion is not None
    entregas = notification_repository.entregas_de(notificacion.id)
    email = [entrega for entrega in entregas if entrega.canal.value == "email"]
    assert len(email) == 1
    assert email[0].estado == "fallido"
    assert email[0].intentos == client.app.state.settings.notification_max_retries
    _, total = servicio.bandeja(tipo_cuenta(cuenta_id))
    assert total == 1
