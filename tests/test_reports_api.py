"""Pruebas de aceptación de HU-12: reportes y sanciones."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from app.domain.product import ESTADO_ARCHIVADO, ESTADO_PUBLICADO
from app.domain.report import (
    CAT_16,
    EVENTO_REPORTE_CREADO,
    EVENTO_REPORTE_RESUELTO,
    EVENTO_SANCION_APLICADA,
)
from app.repository.notifications import notification_repository
from tests.conftest import PRODUCTS_URL

REPORTS_URL = "/api/v1/catalog/reports"
CONTROL_URL = "/api/v1/catalog/publication-control"

ADMIN = {"X-Actor-Id": "usr_admin", "X-Actor-Roles": "administrador"}
CONSUMIDOR = {"X-Actor-Id": "usr_020", "X-Actor-Roles": "consumidor"}
PRODUCTOR = {"X-Actor-Id": "usr_010", "X-Actor-Roles": "productor"}
EVIDENCIA = "Captura de pantalla del contenido infractor."
MOTIVO = "derechos_autor"


@pytest.fixture(autouse=True)
def _reset_notificaciones() -> Any:
    notification_repository.reset()
    yield
    notification_repository.reset()


def _body(response) -> dict[str, Any]:
    return response.json()


def _crear_reporte(
    client: TestClient,
    contenido_id: str,
    *,
    motivo: str = MOTIVO,
    evidencia: Any = EVIDENCIA,
    headers: dict[str, str] | None = None,
    **cambios: Any,
):
    payload: dict[str, Any] = {
        "contenidoId": contenido_id,
        "motivo": motivo,
        "evidencia": evidencia,
    }
    payload.update(cambios)
    return client.post(REPORTS_URL, json=payload, headers=headers or CONSUMIDOR)


def _crear_producto(
    client: TestClient, create_product: Callable[..., Any], **cambios: Any
) -> str:
    respuesta = create_product(headers=PRODUCTOR, **cambios)
    assert respuesta.status_code == 201
    return _body(respuesta)["data"]["id"]


def _bandeja(cuenta_id: str) -> list[Any]:
    items, _ = notification_repository.listar(
        cuenta_id,
        ahora=datetime.now(timezone.utc) + timedelta(seconds=1),
        limite=20,
        offset=0,
    )
    return items


# Caso 1: reporte válido ----------------------------------------------------
def test_reporte_valido_devuelve_201_y_reporte_abierto(
    client: TestClient, create_product: Callable[..., Any]
):
    producto_id = _crear_producto(client, create_product)

    respuesta = _crear_reporte(client, producto_id)

    assert respuesta.status_code == 201
    cuerpo = _body(respuesta)
    assert cuerpo["message"] == "Reporte registrado correctamente."
    assert cuerpo["success"] is True
    datos = cuerpo["data"]
    assert datos["id"].startswith("rep_")
    assert datos["contenidoId"] == producto_id
    assert datos["motivo"] == MOTIVO
    assert datos["estado"] == "abierto"
    assert datos["fecha"]
    assert datos["evidencia"] == EVIDENCIA
    assert "reportanteId" not in datos
    assert "reportante" not in datos


def test_reporte_registra_evento_auditoria_y_notifica_al_reportante(
    client: TestClient, create_product: Callable[..., Any]
):
    producto_id = _crear_producto(client, create_product)
    respuesta = _crear_reporte(client, producto_id)
    reporte_id = _body(respuesta)["data"]["id"]

    eventos = client.app.state.event_bus.events(EVENTO_REPORTE_CREADO)
    assert len(eventos) == 1
    assert eventos[0]["payload"]["reporteId"] == reporte_id
    assert eventos[0]["payload"]["contenidoId"] == producto_id
    assert "reportante" not in eventos[0]["payload"]

    auditoria = client.app.state.report_service.audit_repository.list_for_entity(
        reporte_id, entidad="reporte"
    )
    assert auditoria[-1]["accion"] == "crear_reporte"
    assert auditoria[-1]["actorId"] == "usr_020"
    assert auditoria[-1]["cambios"]["motivo"] == MOTIVO
    assert auditoria[-1]["cambios"]["evidencia"] == EVIDENCIA

    notificaciones = _bandeja("usr_020")
    assert len(notificaciones) == 1
    assert notificaciones[0].tipo.value == "reporte_recibido"
    assert MOTIVO in notificaciones[0].mensaje


# Caso 2: motivo inválido ---------------------------------------------------
def test_motivo_desconocido_devuelve_400(client: TestClient):
    respuesta = _crear_reporte(client, "prod_999", motivo="motivo_inexistente")

    assert respuesta.status_code == 400
    assert _body(respuesta)["data"]["codigo"] == "REPORT_REASON_INVALID"
    assert _body(client.get(f"{CONTROL_URL}/reports", headers=ADMIN))["data"]["total"] == 0


def test_evidencia_vacia_devuelve_400(client: TestClient):
    respuesta = _crear_reporte(client, "prod_999", evidencia="   ")

    assert respuesta.status_code == 400
    assert _body(respuesta)["data"]["codigo"] == "REPORT_EVIDENCE_REQUIRED"


# Caso 3: reporte duplicado -------------------------------------------------
def test_reporte_duplicado_abierto_devuelve_409(
    client: TestClient, create_product: Callable[..., Any]
):
    producto_id = _crear_producto(client, create_product)
    assert _crear_reporte(client, producto_id).status_code == 201

    duplicado = _crear_reporte(client, producto_id, motivo="contenido_inseguro")

    assert duplicado.status_code == 409
    assert _body(duplicado)["data"]["codigo"] == "REPORT_DUPLICATE"


def test_otro_usuario_puede_reportar_el_mismo_contenido(
    client: TestClient, create_product: Callable[..., Any]
):
    producto_id = _crear_producto(client, create_product)
    assert _crear_reporte(client, producto_id).status_code == 201

    respuesta = _crear_reporte(
        client,
        producto_id,
        headers={"X-Actor-Id": "usr_021", "X-Actor-Roles": "productor"},
    )

    assert respuesta.status_code == 201
    assert _body(client.get(f"{CONTROL_URL}/reports", headers=ADMIN))["data"]["total"] == 2


# FUN-36: consulta y resolución ---------------------------------------------
def test_admin_consulta_cola_con_filtros_y_productor_no_puede(
    client: TestClient, create_product: Callable[..., Any]
):
    producto_id = _crear_producto(client, create_product)
    reporte_id = _body(_crear_reporte(client, producto_id))["data"]["id"]

    respuesta = client.get(
        f"{CONTROL_URL}/reports",
        params={"estado": "abierto", "contenidoId": producto_id},
        headers=ADMIN,
    )

    assert respuesta.status_code == 200
    datos = _body(respuesta)["data"]
    assert datos["total"] == 1
    assert datos["items"][0]["id"] == reporte_id
    assert "reportanteId" not in datos["items"][0]
    assert client.get(f"{CONTROL_URL}/reports", headers=CONSUMIDOR).status_code == 403


# Caso 5: desestimar reporte ------------------------------------------------
def test_desestimar_reporte_devuelve_decision_y_notifica(
    client: TestClient, create_product: Callable[..., Any]
):
    producto_id = _crear_producto(client, create_product)
    reporte_id = _body(_crear_reporte(client, producto_id))["data"]["id"]

    respuesta = client.patch(
        f"{CONTROL_URL}/reports/{reporte_id}",
        json={
            "decision": "desestimar",
            "observacion": "La evidencia no permite confirmar la infracción.",
        },
        headers=ADMIN,
    )

    assert respuesta.status_code == 200
    datos = _body(respuesta)["data"]
    assert datos["estado"] == "resuelto"
    assert datos["decision"] == "desestimado"
    assert datos["resolucion"] == {
        "decision": "desestimado",
        "sancion": None,
        "observacion": "La evidencia no permite confirmar la infracción.",
        "fecha": datos["resolucion"]["fecha"],
    }
    assert _body(client.get(f"{CONTROL_URL}/reports/{reporte_id}", headers=ADMIN))[
        "data"
    ]["estado"] == "resuelto"

    eventos = client.app.state.event_bus.events(EVENTO_REPORTE_RESUELTO)
    assert eventos[0]["payload"]["decision"] == "desestimado"
    notificaciones = _bandeja("usr_020")
    assert any(item.tipo.value == "reporte_resuelto" for item in notificaciones)
    assert any("desestimado" in item.mensaje for item in notificaciones)


# Caso 4: aplicar suspensión ------------------------------------------------
def test_suspension_temporal_cat16_archiva_y_notifica(
    client: TestClient, create_product: Callable[..., Any], product_service
):
    producto_id = _crear_producto(client, create_product, nombre="Pack sancionado")
    producto = product_service.repository.get(producto_id)
    producto.estado = ESTADO_PUBLICADO
    producto.activo = True
    product_service.repository.update(producto)
    reporte_id = _body(_crear_reporte(client, producto_id))["data"]["id"]

    respuesta = client.post(
        f"{CONTROL_URL}/sanctions",
        json={
            "reporteId": reporte_id,
            "tipo": "suspension_temporal",
            "duracionDias": 10,
            "motivo": MOTIVO,
            "observacion": "Uso no autorizado de ilustraciones.",
        },
        headers=ADMIN,
    )

    assert respuesta.status_code == 201
    datos = _body(respuesta)["data"]
    assert datos["tipo"] == "suspension_temporal"
    assert datos["duracionDias"] == 10
    assert datos["usuarioAfectado"] == "usr_010"
    assert datos["politica"] == "CAT-15"
    assert datos["estadoContenido"] == ESTADO_ARCHIVADO
    assert datos["notificado"] is True

    reporte = _body(client.get(f"{CONTROL_URL}/reports/{reporte_id}", headers=ADMIN))[
        "data"
    ]
    assert reporte["estado"] == "resuelto"
    assert reporte["decision"] == "sancionado"
    assert reporte["sancion"] == datos["id"]

    assert _body(client.get(f"{PRODUCTS_URL}/{producto_id}"))["data"]["estado"] == ESTADO_ARCHIVADO
    assert all(
        item["id"] != producto_id
        for item in _body(client.get(f"{PRODUCTS_URL}?q=sancionado"))["data"]["items"]
    )

    eventos = client.app.state.event_bus.events(EVENTO_SANCION_APLICADA)
    assert len(eventos) == 1
    assert eventos[0]["payload"]["duracionDias"] == 10
    assert eventos[0]["payload"]["usuarioAfectado"] == "usr_010"

    afectado = _bandeja("usr_010")
    assert any(item.tipo.value == "sancion_aplicada" for item in afectado)
    assert any("10 días" in item.mensaje for item in afectado)
    assert any("CAT-16" in item.mensaje for item in afectado)
    assert any(item.tipo.value == "reporte_resuelto" for item in _bandeja("usr_020"))

    auditoria = client.app.state.report_service.audit_repository.list_for_entity(
        datos["id"], entidad="sancion"
    )
    assert auditoria[-1]["accion"] == "aplicar_sancion"
    assert auditoria[-1]["cambios"]["duracionPolitica"] == CAT_16
    assert auditoria[-1]["cambios"]["evidencia"] == EVIDENCIA


def test_suspension_sin_duracion_usa_cat16(
    client: TestClient, create_product: Callable[..., Any]
):
    producto_id = _crear_producto(client, create_product)
    reporte_id = _body(_crear_reporte(client, producto_id))["data"]["id"]

    respuesta = client.post(
        f"{CONTROL_URL}/sanctions",
        json={"reporteId": reporte_id, "tipo": "suspension"},
        headers=ADMIN,
    )

    assert respuesta.status_code == 201
    assert _body(respuesta)["data"]["duracionDias"] == 7


def test_tipo_de_sancion_invalido_devuelve_400(client: TestClient):
    respuesta = client.post(
        f"{CONTROL_URL}/sanctions",
        json={
            "contenidoId": "prod_404",
            "tipo": "sancion_desconocida",
            "usuarioAfectado": "usr_010",
            "evidencia": EVIDENCIA,
        },
        headers=ADMIN,
    )

    assert respuesta.status_code == 400
    assert _body(respuesta)["data"]["codigo"] == "SANCTION_TYPE_INVALID"


def test_resolver_con_sancion_crea_sancion_cat15(
    client: TestClient, create_product: Callable[..., Any]
):
    producto_id = _crear_producto(client, create_product)
    reporte_id = _body(_crear_reporte(client, producto_id))["data"]["id"]

    respuesta = client.patch(
        f"{CONTROL_URL}/reports/{reporte_id}",
        json={
            "decision": "sancionar",
            "observacion": "Se confirma la infracción.",
            "sancion": {
                "tipo": "restriccion_contenido",
                "accionContenido": "restringir",
                "usuarioAfectado": "usr_010",
            },
        },
        headers=ADMIN,
    )

    assert respuesta.status_code == 200
    assert _body(respuesta)["data"]["decision"] == "sancionado"
    sanciones = _body(client.get(f"{CONTROL_URL}/sanctions", headers=ADMIN))["data"]
    assert sanciones["total"] == 1
    assert sanciones["items"][0]["tipo"] == "restriccion_contenido"
    assert sanciones["items"][0]["accionContenido"] == "restringir"
    assert client.app.state.event_bus.events(EVENTO_SANCION_APLICADA)


def test_reporte_resuelto_no_puede_resolverse_dos_veces(
    client: TestClient, create_product: Callable[..., Any]
):
    producto_id = _crear_producto(client, create_product)
    reporte_id = _body(_crear_reporte(client, producto_id))["data"]["id"]
    primera = client.patch(
        f"{CONTROL_URL}/reports/{reporte_id}",
        json={"decision": "desestimar"},
        headers=ADMIN,
    )
    assert primera.status_code == 200

    segunda = client.patch(
        f"{CONTROL_URL}/reports/{reporte_id}",
        json={"decision": "sancionar", "sancion": {"tipo": "advertencia"}},
        headers=ADMIN,
    )

    assert segunda.status_code == 409
    assert _body(segunda)["data"]["codigo"] == "REPORT_INVALID_STATE"


def test_reportes_y_sanciones_no_rompen_catalogo(
    client: TestClient, create_product: Callable[..., Any]
):
    assert _crear_producto(client, create_product)
    assert client.get(PRODUCTS_URL).status_code == 200
    assert client.get(f"{CONTROL_URL}/reports", headers=ADMIN).status_code == 200
