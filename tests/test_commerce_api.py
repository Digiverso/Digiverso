"""Pruebas de aceptación de HU-15 sobre la API de Comercio."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app.domain.exceptions import InvalidPurchaseStateError
from app.domain.publication_review import CHECKLIST_ITEMS
from tests.conftest import PRODUCTS_URL

LICENSES_URL = "/api/v1/commerce/licenses"
PURCHASES_URL = "/api/v1/commerce/purchases"
DOWNLOADS_URL = "/api/v1/commerce/downloads"
CONTROL_URL = "/api/v1/catalog/publication-control"

BUYER = {"X-Actor-Id": "usr_001", "X-Actor-Roles": "consumidor"}
OTHER_BUYER = {"X-Actor-Id": "usr_002", "X-Actor-Roles": "consumidor"}
PRODUCER = {"X-Actor-Id": "usr_010", "X-Actor-Roles": "productor"}
ADMIN = {"X-Actor-Id": "usr_admin", "X-Actor-Roles": "administrador"}


def _body(response) -> dict[str, Any]:
    return response.json()


def _producto_publicado(
    client: TestClient, create_product: Callable[..., Any], nombre: str = "Pack de ilustraciones"
) -> str:
    product_id = _body(
        create_product(headers=PRODUCER, nombre=nombre)
    )["data"]["id"]
    assert client.post(
        f"{PRODUCTS_URL}/{product_id}/submit-review", headers=PRODUCER
    ).status_code == 200
    aprobacion = client.patch(
        f"{CONTROL_URL}/{product_id}/approve",
        json={"checklist": {item: True for item in CHECKLIST_ITEMS}},
        headers=ADMIN,
    )
    assert aprobacion.status_code == 200
    return product_id


def _compra_con_licencia(
    client: TestClient, create_product: Callable[..., Any], nombre: str = "Pack de ilustraciones"
):
    product_id = _producto_publicado(client, create_product, nombre)
    servicio = client.app.state.commerce_service
    compra = servicio.register_paid_purchase(product_id, "usr_001")
    licencia = servicio.emit_license(compra["id"])
    return product_id, compra, licencia


# Caso 1: consultar licencia -------------------------------------------------
def test_consultar_licencia_activa(
    client: TestClient, create_product: Callable[..., Any]
):
    _, compra, licencia = _compra_con_licencia(client, create_product)

    respuesta = client.get(f"{LICENSES_URL}/{licencia['id']}", headers=BUYER)

    assert respuesta.status_code == 200
    cuerpo = _body(respuesta)
    assert cuerpo["success"] is True
    assert cuerpo["message"] == "Licencia consultada correctamente."
    assert set(cuerpo["data"]) == {
        "id",
        "productoId",
        "compradorId",
        "estado",
        "condiciones",
        "fechaEmision",
    }
    assert cuerpo["data"]["id"] == licencia["id"]
    assert cuerpo["data"]["productoId"] == compra["productoId"]
    assert cuerpo["data"]["compradorId"] == "usr_001"
    assert cuerpo["data"]["estado"] == "activa"
    assert cuerpo["data"]["condiciones"] == "Uso personal, sin edición ni reventa"


def test_consultar_licencia_ajena_y_sin_actor(
    client: TestClient, create_product: Callable[..., Any]
):
    _, _, licencia = _compra_con_licencia(client, create_product)

    ajena = client.get(f"{LICENSES_URL}/{licencia['id']}", headers=OTHER_BUYER)
    assert ajena.status_code == 403
    assert _body(ajena)["data"]["codigo"] == "LICENSE_FORBIDDEN"

    sin_actor = client.get(f"{LICENSES_URL}/{licencia['id']}")
    assert sin_actor.status_code == 401
    assert _body(sin_actor)["data"]["codigo"] == "CONSUMER_REQUIRED"


def test_licencia_inexistente(client: TestClient):
    respuesta = client.get(f"{LICENSES_URL}/lic_999", headers=BUYER)
    assert respuesta.status_code == 404
    assert _body(respuesta)["data"]["codigo"] == "LICENSE_NOT_FOUND"


# Caso 2: descarga con licencia ----------------------------------------------
def test_descarga_con_licencia_devuelve_url_firmada_y_audita(
    client: TestClient,
    create_product: Callable[..., Any],
    clock: dict[str, datetime],
):
    _, compra, licencia = _compra_con_licencia(client, create_product)
    headers = dict(BUYER, **{"X-Forwarded-For": "203.0.113.9"})

    respuesta = client.get(
        f"{PURCHASES_URL}/{compra['id']}/download", headers=headers
    )

    assert respuesta.status_code == 200
    datos = _body(respuesta)["data"]
    assert set(datos) == {"url", "expiraEn", "nombreArchivo"}
    token = urlsplit(datos["url"]).path.rsplit("/", 1)[-1]
    assert token.count(".") == 1
    assert f"{DOWNLOADS_URL}/" in datos["url"]
    expira = datetime.fromisoformat(datos["expiraEn"])
    assert expira == clock["now"] + timedelta(
        minutes=client.app.state.commerce_service.settings.commerce_download_ttl_minutes
    )
    assert datos["nombreArchivo"] == "pack-de-ilustraciones.webp"

    servicio = client.app.state.commerce_service
    assert servicio.repository.count_downloads(licencia["id"]) == 1
    eventos = servicio.audit_repository.list_for_entity(
        compra["id"], entidad="descarga"
    )
    assert len(eventos) == 1
    assert eventos[0]["accion"] == "descarga_autorizada"
    assert eventos[0]["actorId"] == "usr_001"
    assert eventos[0]["cambios"]["ip"] == "203.0.113.9"
    assert eventos[0]["cambios"]["licenciaId"] == licencia["id"]


def test_url_firmada_valida_redirige_al_objeto(
    client: TestClient, create_product: Callable[..., Any]
):
    _, compra, _ = _compra_con_licencia(client, create_product)
    datos = _body(
        client.get(f"{PURCHASES_URL}/{compra['id']}/download", headers=BUYER)
    )["data"]
    token = urlsplit(datos["url"]).path.rsplit("/", 1)[-1]

    acceso = client.get(f"{DOWNLOADS_URL}/{token}", follow_redirects=False)

    assert acceso.status_code == 307
    assert acceso.headers["location"].startswith("https://storage.digiverso.test/")


# Caso 3: descarga sin licencia ----------------------------------------------
def test_descarga_sin_licencia_devuelve_403(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _producto_publicado(client, create_product)
    compra = client.app.state.commerce_service.repository.register_purchase(
        product_id,
        "usr_001",
        estado="pagada",
        fecha_creacion=datetime.now(timezone.utc),
    )

    respuesta = client.get(f"{PURCHASES_URL}/{compra['id']}/download", headers=BUYER)

    assert respuesta.status_code == 403
    assert _body(respuesta)["data"]["codigo"] == "LICENSE_REQUIRED"


def test_descarga_de_compra_ajena_y_sin_actor(
    client: TestClient, create_product: Callable[..., Any]
):
    _, compra, _ = _compra_con_licencia(client, create_product)

    ajena = client.get(
        f"{PURCHASES_URL}/{compra['id']}/download", headers=OTHER_BUYER
    )
    assert ajena.status_code == 403
    assert _body(ajena)["data"]["codigo"] == "LICENSE_FORBIDDEN"

    sin_actor = client.get(f"{PURCHASES_URL}/{compra['id']}/download")
    assert sin_actor.status_code == 401


# Caso 4: URL expirada -------------------------------------------------------
def test_url_expirada_devuelve_410(
    client: TestClient, create_product: Callable[..., Any], clock: dict[str, datetime]
):
    _, compra, _ = _compra_con_licencia(client, create_product)
    datos = _body(
        client.get(f"{PURCHASES_URL}/{compra['id']}/download", headers=BUYER)
    )["data"]
    token = urlsplit(datos["url"]).path.rsplit("/", 1)[-1]

    clock["now"] += timedelta(
        minutes=client.app.state.commerce_service.settings.commerce_download_ttl_minutes + 1
    )
    respuesta = client.get(f"{DOWNLOADS_URL}/{token}", follow_redirects=False)

    assert respuesta.status_code == 410
    assert _body(respuesta)["data"]["codigo"] == "URL_EXPIRED"


def test_url_con_firma_invalida_devuelve_403(
    client: TestClient, create_product: Callable[..., Any]
):
    _, compra, _ = _compra_con_licencia(client, create_product)
    datos = _body(
        client.get(f"{PURCHASES_URL}/{compra['id']}/download", headers=BUYER)
    )["data"]
    token = urlsplit(datos["url"]).path.rsplit("/", 1)[-1]
    cuerpo, firma = token.split(".", 1)
    manipulada = f"{cuerpo}.{firma[:-1]}{'a' if firma[-1] != 'a' else 'b'}"

    respuesta = client.get(f"{DOWNLOADS_URL}/{manipulada}", follow_redirects=False)

    assert respuesta.status_code == 403
    assert _body(respuesta)["data"]["codigo"] == "SIGNATURE_INVALID"


# Caso 5: historial ----------------------------------------------------------
def test_historial_paginado_y_ordenado_por_fecha(
    client: TestClient, create_product: Callable[..., Any], clock: dict[str, datetime]
):
    servicio = client.app.state.commerce_service
    _, primera, licencia_primera = _compra_con_licencia(
        client, create_product, "Primer producto"
    )
    clock["now"] += timedelta(minutes=5)
    _, segunda, licencia_segunda = _compra_con_licencia(
        client, create_product, "Segundo producto"
    )

    pagina_1 = client.get(
        f"{PURCHASES_URL}?pagina=1&tamanioPagina=1", headers=BUYER
    )
    assert pagina_1.status_code == 200
    datos = _body(pagina_1)
    assert datos["message"] == "Historial de compras consultado correctamente."
    assert datos["data"]["total"] == 2
    assert datos["data"]["totalPaginas"] == 2
    assert datos["data"]["pagina"] == 1
    assert len(datos["data"]["compras"]) == 1
    assert datos["data"]["compras"][0]["id"] == segunda["id"]
    assert datos["data"]["compras"][0]["estadoLicencia"] == "activa"

    pagina_2 = client.get(
        f"{PURCHASES_URL}?pagina=2&tamanioPagina=1", headers=BUYER
    )
    assert pagina_2.status_code == 200
    assert _body(pagina_2)["data"]["compras"][0]["id"] == primera["id"]
    assert {
        item["id"] for item in _body(pagina_2)["data"]["licencias"]
    } == {licencia_primera["id"], licencia_segunda["id"]}

    otro = client.get(PURCHASES_URL, headers=OTHER_BUYER)
    assert _body(otro)["data"]["total"] == 0
    assert servicio.repository.count_downloads(licencia_primera["id"]) == 0


@pytest.mark.parametrize(
    "query",
    ["?pagina=0", "?tamanioPagina=0", "?tamanioPagina=abc", "?tamanioPagina=101"],
)
def test_historial_rechaza_paginacion_invalida(client: TestClient, query: str):
    respuesta = client.get(f"{PURCHASES_URL}{query}", headers=BUYER)
    assert respuesta.status_code == 400
    assert _body(respuesta)["data"]["codigo"] == "PAGINATION_INVALID"


def test_historial_sin_actor(client: TestClient):
    respuesta = client.get(PURCHASES_URL)
    assert respuesta.status_code == 401
    assert _body(respuesta)["data"]["codigo"] == "CONSUMER_REQUIRED"


# Caso 6: producto archivado -------------------------------------------------
def test_producto_archivado_conserva_descarga(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id, compra, licencia = _compra_con_licencia(client, create_product)

    archivado = client.patch(
        f"{PRODUCTS_URL}/{product_id}/archive", headers=PRODUCER
    )
    assert archivado.status_code == 200
    assert _body(
        client.get(f"{PRODUCTS_URL}/{product_id}", headers=PRODUCER)
    )["data"]["estado"] == "archivado"

    descarga = client.get(
        f"{PURCHASES_URL}/{compra['id']}/download", headers=BUYER
    )
    assert descarga.status_code == 200
    assert _body(descarga)["data"]["url"]
    assert _body(
        client.get(f"{LICENSES_URL}/{licencia['id']}", headers=BUYER)
    )["data"]["estado"] == "activa"


# Emisión y límites ----------------------------------------------------------
def test_licencia_solo_para_orden_pagada_y_es_idempotente(
    client: TestClient, create_product: Callable[..., Any], clock: dict[str, datetime]
):
    product_id = _producto_publicado(client, create_product)
    servicio = client.app.state.commerce_service
    pendiente = servicio.repository.register_purchase(
        product_id,
        "usr_001",
        estado="pendiente",
        fecha_creacion=clock["now"],
    )

    with pytest.raises(InvalidPurchaseStateError):
        servicio.emit_license(pendiente["id"])
    assert servicio.repository.get_purchase(pendiente["id"])["licenciaId"] is None

    compra = servicio.register_paid_purchase(product_id, "usr_001")
    primera = servicio.emit_license(compra["id"])
    segunda = servicio.emit_license(compra["id"])
    assert primera["id"] == segunda["id"]
    eventos = servicio.audit_repository.list_for_entity(
        primera["id"], entidad="licencia"
    )
    assert len(eventos) == 1
    assert eventos[0]["accion"] == "licencia_emitida"


def test_limite_com_09_de_descargas(
    client: TestClient, create_product: Callable[..., Any]
):
    _, compra, licencia = _compra_con_licencia(client, create_product)
    servicio = client.app.state.commerce_service
    servicio.settings = replace(servicio.settings, commerce_max_downloads=1)

    primera = client.get(f"{PURCHASES_URL}/{compra['id']}/download", headers=BUYER)
    segunda = client.get(f"{PURCHASES_URL}/{compra['id']}/download", headers=BUYER)

    assert primera.status_code == 200
    assert segunda.status_code == 403
    assert _body(segunda)["data"]["codigo"] == "DOWNLOAD_LIMIT_REACHED"
    assert servicio.repository.count_downloads(licencia["id"]) == 1
