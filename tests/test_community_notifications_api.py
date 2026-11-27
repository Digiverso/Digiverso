"""Pruebas de notificaciones de comunidad (HU-20, FUN-63)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.repository.auth_repository import auth_repository
from app.repository.community_notifications import community_notification_store
from app.repository.email_repository import EmailDelivery
from app.repository.notifications import notification_repository
from app.services.community_notifications import CommunityNotificationConsumer
from tests.conftest import PASSWORD, extraer_token, payload_registro

COMUNIDAD_URL = "/api/v1/users/me/notifications/comunidad"
BANDEJA_URL = "/api/v1/users/me/notifications"
PREFERENCIAS_URL = "/api/v1/users/me/notification-preferences"


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
            message_id="fake_hu20",
            estado="enviado",
            intento_en=datetime.now(),
        )


@pytest.fixture(autouse=True)
def _reset_notificaciones() -> Any:
    notification_repository.reset()
    community_notification_store.reset()
    yield
    notification_repository.reset()
    community_notification_store.reset()


def crear_cuenta(client: TestClient, email_gateway, correo: str) -> str:
    respuesta = client.post(
        "/api/v1/auth/register", json=payload_registro(correo=correo)
    )
    token = extraer_token(email_gateway)
    client.post("/api/v1/auth/email/verify", json={"token": token})
    return str(respuesta.json()["data"]["userId"])


def headers_de(client: TestClient, correo: str) -> dict[str, str]:
    respuesta = client.post(
        "/api/v1/auth/login", json={"correo": correo, "password": PASSWORD}
    )
    token = respuesta.json()["data"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def consumidor_de(
    client: TestClient,
    clock: dict[str, datetime],
    sender: FakeNotificationSender | None = None,
    *,
    comu11_enabled: bool | None = None,
    product_author_provider: Any = None,
) -> CommunityNotificationConsumer:
    return CommunityNotificationConsumer(
        repo=notification_repository,
        settings=client.app.state.settings,
        store=community_notification_store,
        clock=lambda: clock["now"],
        sender=sender,
        account_provider=lambda cuenta_id: auth_repository.obtener_cuenta_por_id(
            cuenta_id
        ),
        product_author_provider=product_author_provider,
        comu11_enabled=comu11_enabled,
    )


def test_nuevo_seguidor_genera_notificacion_en_bandeja(
    client: TestClient, email_gateway, clock: dict[str, datetime]
) -> None:
    receptora = crear_cuenta(client, email_gateway, "ana@example.com")
    seguidor = crear_cuenta(client, email_gateway, "bob@example.com")
    servicio = consumidor_de(client, clock)

    datos = servicio.procesar_evento(
        "user.followed",
        {
            "id": "follow_1",
            "seguidorId": seguidor,
            "seguidoId": receptora,
            "seguidorNombre": "Bob Pérez",
        },
    )

    assert datos is not None
    assert datos.tipo == "nuevo_seguidor"
    assert datos.emisor == "Bob Pérez"
    assert datos.mensaje == "Bob Pérez comenzó a seguirte."
    assert datos.leida is False

    bandeja = client.get(COMUNIDAD_URL, headers=headers_de(client, "ana@example.com"))
    assert bandeja.status_code == 200
    cuerpo = bandeja.json()
    assert cuerpo["data"]["total"] == 1
    assert set(cuerpo["data"]["items"][0]) == {
        "id",
        "tipo",
        "emisor",
        "mensaje",
        "leida",
        "fecha",
    }
    assert cuerpo["data"]["items"][0]["emisor"] == "Bob Pérez"

    general = client.get(BANDEJA_URL, headers=headers_de(client, "ana@example.com"))
    assert general.json()["data"]["total"] == 1


def test_comu11_desactivado_no_genera_notificacion(
    client: TestClient, email_gateway, clock: dict[str, datetime]
) -> None:
    receptora = crear_cuenta(client, email_gateway, "ana@example.com")
    seguidor = crear_cuenta(client, email_gateway, "bob@example.com")
    servicio = consumidor_de(client, clock, comu11_enabled=False)

    assert (
        servicio.procesar_evento(
            "user.followed",
            {"id": "f1", "seguidorId": seguidor, "seguidoId": receptora},
        )
        is None
    )
    bandeja = client.get(BANDEJA_URL, headers=headers_de(client, "ana@example.com"))
    assert bandeja.json()["data"]["total"] == 0


def test_no_se_notifica_al_emisor_de_la_accion(
    client: TestClient, email_gateway, clock: dict[str, datetime]
) -> None:
    usuario = crear_cuenta(client, email_gateway, "ana@example.com")
    servicio = consumidor_de(client, clock)

    assert (
        servicio.procesar_evento(
            "user.followed",
            {"id": "f2", "seguidorId": usuario, "seguidoId": usuario},
        )
        is None
    )
    bandeja = client.get(BANDEJA_URL, headers=headers_de(client, "ana@example.com"))
    assert bandeja.json()["data"]["total"] == 0


def test_reintento_no_duplica_notificacion(
    client: TestClient, email_gateway, clock: dict[str, datetime]
) -> None:
    receptora = crear_cuenta(client, email_gateway, "ana@example.com")
    seguidor = crear_cuenta(client, email_gateway, "bob@example.com")
    sender = FakeNotificationSender(fallos=99)
    servicio = consumidor_de(client, clock, sender)

    evento = {
        "id": "follow_retry",
        "seguidorId": seguidor,
        "seguidoId": receptora,
        "nombre": "Bob Pérez",
    }
    primera = servicio.procesar_evento("user.followed", evento)
    segunda = servicio.procesar_evento("user.followed", evento)

    assert primera is not None and segunda is not None
    assert primera.id == segunda.id
    bandeja = client.get(BANDEJA_URL, headers=headers_de(client, "ana@example.com"))
    assert bandeja.json()["data"]["total"] == 1

    entregas = notification_repository.entregas_de(primera.id)
    email = [entrega for entrega in entregas if entrega.canal.value == "email"]
    assert len(email) == 1
    assert email[0].estado == "fallido"
    assert email[0].intentos == client.app.state.settings.notification_max_retries
    assert {entrega.canal.value for entrega in entregas} == {"email", "in_app"}


def test_resena_notifica_al_productor_sin_exponer_el_texto(
    client: TestClient, email_gateway, clock: dict[str, datetime]
) -> None:
    productor = crear_cuenta(client, email_gateway, "ana@example.com")
    evaluador = crear_cuenta(client, email_gateway, "bob@example.com")
    servicio = consumidor_de(
        client, clock, product_author_provider=lambda producto_id: productor
    )

    datos = servicio.procesar_evento(
        "review.created",
        {
            "id": "review_1",
            "productId": "prod_1",
            "userId": evaluador,
            "calificacion": 5,
            "texto": "informacion privada del comprador",
            "nombre": "Bob Pérez",
        },
    )

    assert datos is not None
    assert datos.tipo == "nueva_resena"
    assert datos.mensaje == "Bob Pérez calificó tu producto con 5 estrellas."
    assert "informacion privada" not in datos.mensaje
    bandeja = client.get(COMUNIDAD_URL, headers=headers_de(client, "ana@example.com"))
    assert bandeja.json()["data"]["items"][0]["mensaje"] == datos.mensaje


def test_preferencias_aut_10_se_respetan_antes_de_entregar(
    client: TestClient, email_gateway, clock: dict[str, datetime]
) -> None:
    receptora = crear_cuenta(client, email_gateway, "ana@example.com")
    seguidor = crear_cuenta(client, email_gateway, "bob@example.com")
    cabeceras = headers_de(client, "ana@example.com")
    preferencias = client.put(
        PREFERENCIAS_URL,
        json={"canales": ["in_app"], "tipos": ["nuevo_seguidor"]},
        headers=cabeceras,
    )
    assert preferencias.status_code == 200

    servicio = consumidor_de(client, clock)
    datos = servicio.procesar_evento(
        "user.followed",
        {"id": "f3", "seguidorId": seguidor, "seguidoId": receptora},
    )
    assert datos is not None
    assert {e.canal.value for e in notification_repository.entregas_de(datos.id)} == {
        "in_app"
    }

    sin_tipo = client.put(
        PREFERENCIAS_URL,
        json={"canales": ["in_app"], "tipos": []},
        headers=cabeceras,
    )
    assert sin_tipo.status_code == 200
    assert (
        servicio.procesar_evento(
            "user.followed",
            {"id": "f4", "seguidorId": seguidor, "seguidoId": receptora},
        )
        is None
    )


def test_retencion_aut_11_y_lectura(
    client: TestClient, email_gateway, clock: dict[str, datetime]
) -> None:
    receptora = crear_cuenta(client, email_gateway, "ana@example.com")
    seguidor = crear_cuenta(client, email_gateway, "bob@example.com")
    servicio = consumidor_de(client, clock)
    datos = servicio.procesar_evento(
        "user.followed",
        {"id": "f5", "seguidorId": seguidor, "seguidoId": receptora},
    )
    assert datos is not None

    cabeceras = headers_de(client, "ana@example.com")
    leida = client.patch(f"{BANDEJA_URL}/{datos.id}/read", headers=cabeceras)
    assert leida.status_code == 200

    dias = client.app.state.settings.notification_retention_days
    clock["now"] = clock["now"] + timedelta(days=dias + 1)
    bandeja = client.get(
        COMUNIDAD_URL, headers=headers_de(client, "ana@example.com")
    )
    assert bandeja.json()["data"] == {"items": [], "pagina": 1, "total": 0}


def test_emisor_sanitizado_y_eventos_por_lote(
    client: TestClient, email_gateway, clock: dict[str, datetime]
) -> None:
    receptora = crear_cuenta(client, email_gateway, "ana@example.com")
    seguidor = crear_cuenta(client, email_gateway, "bob@example.com")
    servicio = consumidor_de(client, clock)

    generadas = servicio.consumir_lote(
        [
            {
                "topic": "user.followed",
                "payload": {
                    "id": "f6",
                    "seguidorId": seguidor,
                    "seguidoId": receptora,
                    "nombre": "<b>Bob</b> bob@correo.com https://x.co",
                },
            },
            {"topic": "otro.evento", "payload": {"id": "x"}},
        ]
    )

    assert len(generadas) == 1
    assert generadas[0].emisor == "Bob"
    assert "@" not in generadas[0].mensaje
