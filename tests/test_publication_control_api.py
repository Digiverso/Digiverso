"""Pruebas de aceptación de HU-11 sobre la API de control de publicaciones."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from app.domain.product import ESTADO_RECHAZADO
from app.domain.publication_review import CHECKLIST_ITEMS, EVENTO_PRODUCT_REVIEWED
from app.repository.notifications import notification_repository
from tests.conftest import CATEGORIES_URL, PRODUCTS_URL

QUEUE_URL = "/api/v1/catalog/publication-control/queue"
CONTROL_URL = "/api/v1/catalog/publication-control"

ADMIN = {"X-Actor-Id": "usr_admin", "X-Actor-Roles": "administrador"}
PRODUCTOR = {"X-Actor-Id": "usr_010", "X-Actor-Roles": "productor"}
CHECKLIST = {item: True for item in CHECKLIST_ITEMS}


@pytest.fixture(autouse=True)
def _reset_notificaciones() -> Any:
    notification_repository.reset()
    yield
    notification_repository.reset()


def _body(response) -> dict[str, Any]:
    return response.json()


def _id(response) -> str:
    return _body(response)["data"]["id"]


def _en_revision(
    client: TestClient, create_product: Callable[..., Any], **cambios: object
) -> str:
    product_id = _id(create_product(headers=PRODUCTOR, **cambios))
    respuesta = client.post(
        f"{PRODUCTS_URL}/{product_id}/submit-review", headers=PRODUCTOR
    )
    assert respuesta.status_code == 200
    return product_id


def _bandeja(cuenta_id: str) -> list[Any]:
    items, _ = notification_repository.listar(
        cuenta_id,
        ahora=datetime.now(timezone.utc) + timedelta(seconds=1),
        limite=20,
        offset=0,
    )
    return items


# Caso 1: aprobar publicación -------------------------------------------------
def test_aprobar_publicacion_indexa_notifica_y_audita(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _en_revision(client, create_product)

    respuesta = client.patch(
        f"{CONTROL_URL}/{product_id}/approve",
        json={"checklist": CHECKLIST},
        headers=ADMIN,
    )

    assert respuesta.status_code == 200
    cuerpo = _body(respuesta)
    assert cuerpo["success"] is True
    assert cuerpo["message"] == "Publicación aprobada correctamente."
    assert set(cuerpo["data"]) == {
        "productoId",
        "estado",
        "fechaPublicacion",
        "notificado",
    }
    assert cuerpo["data"]["productoId"] == product_id
    assert cuerpo["data"]["estado"] == "publicado"
    assert cuerpo["data"]["notificado"] is True
    assert _body(client.get(f"{PRODUCTS_URL}/{product_id}"))["data"]["estado"] == "publicado"

    #indexación: el producto publicado aparece en la búsqueda.
    resultados = _body(client.get(f"{PRODUCTS_URL}?q=ilustraciones"))
    assert any(item["id"] == product_id for item in resultados["data"]["items"])

    eventos = client.app.state.event_bus.events(EVENTO_PRODUCT_REVIEWED)
    assert len(eventos) == 1
    assert eventos[0]["payload"]["decision"] == "aprobado"
    assert eventos[0]["payload"]["productoId"] == product_id
    assert eventos[0]["payload"]["checklist"] == CHECKLIST

    notificaciones = _bandeja("usr_010")
    assert len(notificaciones) == 1
    assert notificaciones[0].tipo.value == "producto_publicado"
    assert "aprobado" in notificaciones[0].mensaje

    auditoria = client.app.state.publication_control_service.audit_repository.list_for_entity(
        product_id, entidad="producto"
    )
    decision = auditoria[-1]
    assert decision["accion"] == "aprobar_publicacion"
    assert decision["actorId"] == "usr_admin"
    assert decision["cambios"]["evidencia"]["checklist"] == CHECKLIST


# Caso 2: rechazar sin motivo --------------------------------------------------
def test_rechazar_sin_motivo_devuelve_400_y_no_cambia(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _en_revision(client, create_product)

    respuesta = client.patch(
        f"{CONTROL_URL}/{product_id}/reject",
        json={"observacion": "No cumple."},
        headers=ADMIN,
    )

    assert respuesta.status_code == 400
    assert _body(respuesta)["data"]["codigo"] == "REVIEW_DECISION_INVALID"
    assert _body(client.get(f"{PRODUCTS_URL}/{product_id}"))["data"]["estado"] == "en_revision"
    assert client.app.state.event_bus.events(EVENTO_PRODUCT_REVIEWED) == []


def test_rechazar_con_motivo_vacio_devuelve_400(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _en_revision(client, create_product)

    respuesta = client.patch(
        f"{CONTROL_URL}/{product_id}/reject",
        json={"motivo": "   ", "observacion": "Sin detalle."},
        headers=ADMIN,
    )

    assert respuesta.status_code == 400
    assert _body(respuesta)["data"]["codigo"] == "REVIEW_DECISION_INVALID"


def test_rechazar_registra_motivo_y_permite_corregir_y_reenviar(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _en_revision(client, create_product)

    respuesta = client.patch(
        f"{CONTROL_URL}/{product_id}/reject",
        json={
            "motivo": "derechos_no_aclarados",
            "observacion": "Falta el permiso del ilustrador.",
        },
        headers=ADMIN,
    )

    assert respuesta.status_code == 200
    datos = _body(respuesta)["data"]
    assert datos == {
        "productoId": product_id,
        "estado": ESTADO_RECHAZADO,
        "motivo": "derechos_no_aclarados",
        "observacion": "Falta el permiso del ilustrador.",
    }
    notificaciones = _bandeja("usr_010")
    assert len(notificaciones) == 1
    assert notificaciones[0].tipo.value == "producto_rechazado"
    assert "derechos_no_aclarados" in notificaciones[0].mensaje
    assert "Falta el permiso del ilustrador." in notificaciones[0].mensaje

    eventos = client.app.state.event_bus.events(EVENTO_PRODUCT_REVIEWED)
    assert eventos[0]["payload"]["motivo"] == "derechos_no_aclarados"
    assert eventos[0]["payload"]["observacion"] == "Falta el permiso del ilustrador."

    # El productor corrige y reenvía; el administrador aprueba en el nuevo ciclo.
    assert (
        client.patch(
            f"{PRODUCTS_URL}/{product_id}",
            json={"descripcion": "Ilustraciones con licencia documentada."},
            headers=PRODUCTOR,
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{PRODUCTS_URL}/{product_id}/submit-review", headers=PRODUCTOR
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"{CONTROL_URL}/{product_id}/approve",
            json={"checklist": CHECKLIST},
            headers=ADMIN,
        ).status_code
        == 200
    )
    assert len(_bandeja("usr_010")) == 2


# Caso 3: acceso no administrador ---------------------------------------------
def test_productor_no_puede_consultar_la_cola(client: TestClient):
    respuesta = client.get(QUEUE_URL, headers=PRODUCTOR)

    assert respuesta.status_code == 403
    assert _body(respuesta)["data"]["codigo"] == "REVIEW_FORBIDDEN"


# Caso 4: separación de funciones ---------------------------------------------
def test_administrador_no_puede_revisar_producto_propio(
    client: TestClient, create_product: Callable[..., Any]
):
    admin_autor = {
        "X-Actor-Id": "usr_admin",
        "X-Actor-Roles": "administrador,productor",
    }
    product_id = _id(create_product(headers=admin_autor))
    client.post(f"{PRODUCTS_URL}/{product_id}/submit-review", headers=admin_autor)

    aprobacion = client.patch(
        f"{CONTROL_URL}/{product_id}/approve",
        json={"checklist": CHECKLIST},
        headers=admin_autor,
    )
    rechazo = client.patch(
        f"{CONTROL_URL}/{product_id}/reject",
        json={"motivo": "otro", "observacion": "Conflicto de interés."},
        headers=admin_autor,
    )

    assert aprobacion.status_code == rechazo.status_code == 403
    assert (
        _body(aprobacion)["data"]["codigo"] == "REVIEW_SEPARATION_OF_DUTIES"
    )
    assert _body(client.get(f"{PRODUCTS_URL}/{product_id}"))["data"]["estado"] == "en_revision"


# Caso 5 y estructura de la cola ------------------------------------------------
def test_cola_solo_en_revision_ordenada_por_fecha_de_envio(
    client: TestClient, create_product: Callable[..., Any], product_service
):
    reciente = _en_revision(client, create_product, nombre="Pack reciente")
    antiguo = _en_revision(client, create_product, nombre="Pack antiguo")
    borrador = _id(create_product(headers=PRODUCTOR, nombre="Pack borrador"))

    ahora = datetime.now(timezone.utc)
    for product_id, fecha in (
        (antiguo, ahora - timedelta(hours=3)),
        (reciente, ahora - timedelta(minutes=5)),
    ):
        product = product_service.repository.get(product_id)
        product.estado_desde = fecha
        product_service.repository.update(product)

    respuesta = client.get(QUEUE_URL, headers=ADMIN)

    assert respuesta.status_code == 200
    datos = _body(respuesta)["data"]
    assert datos["total"] == 2
    assert [item["producto"]["id"] for item in datos["items"]] == [antiguo, reciente]
    assert borrador not in [item["producto"]["id"] for item in datos["items"]]
    primero = datos["items"][0]
    assert set(primero) == {
        "producto",
        "autor",
        "fechaEnvio",
        "medios",
        "politicasAplicables",
    }
    assert primero["autor"] == {"id": "usr_010", "nombre": "Autor Digiverso"}
    assert primero["medios"][0]["tipo"] == "imagen"
    assert {politica["codigo"] for politica in primero["politicasAplicables"]} >= {
        "CAT-01",
        "CAT-03",
        "CAT-09",
        "CAT-14",
    }


def test_checklist_incompleto_devuelve_400_y_no_cambia(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _en_revision(client, create_product)

    respuesta = client.patch(
        f"{CONTROL_URL}/{product_id}/approve",
        json={"checklist": {"autoria": True, "edad": True}},
        headers=ADMIN,
    )

    assert respuesta.status_code == 400
    assert _body(respuesta)["data"]["faltantes"] == ["derechos", "contenido", "funciones"]
    assert _body(client.get(f"{PRODUCTS_URL}/{product_id}"))["data"]["estado"] == "en_revision"


def test_producto_inexistente_devuelve_404(client: TestClient):
    respuesta = client.patch(
        f"{CONTROL_URL}/prod_999/approve",
        json={"checklist": CHECKLIST},
        headers=ADMIN,
    )
    assert respuesta.status_code == 404


def test_categoria_y_productos_requeridos_no_se_rompen(client: TestClient):
    """La cola no altera el comportamiento de HU-07/HU-08."""
    assert client.get(CATEGORIES_URL).status_code == 200
    assert client.get(PRODUCTS_URL).status_code == 200
