"""Pruebas de aceptación de HU-18: reseñas y calificaciones."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from fastapi.testclient import TestClient

from tests.conftest import PRODUCTS_URL
from tests.test_catalog_discovery_api import PRODUCTOR, _categoria, _publicar

REVIEWS_URL = "/api/v1/community/products"
CONSUMIDOR = {"X-Actor-Id": "usr_comprador", "X-Actor-Roles": "consumidor"}
OTRO_CONSUMIDOR = {"X-Actor-Id": "usr_comprador_2", "X-Actor-Roles": "consumidor"}
RESENA = {"calificacion": 5, "texto": "Excelente calidad y entrega inmediata."}


def _body(response) -> dict[str, Any]:
    return response.json()


def _producto(
    client: TestClient, create_product: Callable[..., Any], nombre: str = "Pack de ilustraciones"
) -> str:
    categoria_id = _categoria(client, "Comunidad reseñas")
    return _publicar(client, create_product, categoria_id=categoria_id, nombre=nombre)


def _licencia(client: TestClient, product_id: str, user_id: str = "usr_comprador") -> None:
    client.app.state.product_service.repository.add_license(
        product_id, actor_id=user_id
    )


def _publicar_resena(
    client: TestClient, product_id: str, payload: dict[str, Any] | None = None, **cambios: Any
):
    datos = dict(payload or RESENA)
    datos.update(cambios)
    return client.post(
        f"{REVIEWS_URL}/{product_id}/reviews", json=datos, headers=CONSUMIDOR
    )


# Caso 1: reseña válida ------------------------------------------------------
def test_resena_valida_devuelve_201_y_actualiza_promedio(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _producto(client, create_product)
    _licencia(client, product_id)

    response = _publicar_resena(client, product_id)
    assert response.status_code == 201
    body = _body(response)
    assert body["message"] == "Reseña publicada correctamente."
    assert body["success"] is True
    data = body["data"]
    assert set(data) == {
        "id", "productId", "userId", "calificacion", "texto", "fecha"
    }
    assert data["id"].startswith("rev_")
    assert data["productId"] == product_id
    assert data["userId"] == "usr_comprador"
    assert data["calificacion"] == 5
    assert data["texto"] == RESENA["texto"]
    assert data["fecha"].endswith("Z")

    rating = client.get(f"{REVIEWS_URL}/{product_id}/rating")
    assert rating.status_code == 200
    assert _body(rating)["data"] == {
        "promedio": 5.0,
        "total": 1,
        "distribucion": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 1},
    }
    detalle = client.get(
        f"{PRODUCTS_URL}/{product_id}", headers={"X-Actor-Id": "usr_visitante"}
    )
    assert _body(detalle)["data"]["calificacion"] == 5.0


def test_evento_review_created_publicado(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _producto(client, create_product)
    _licencia(client, product_id)

    response = _publicar_resena(client, product_id)
    eventos = client.app.state.event_bus.events("review.created")

    assert response.status_code == 201
    assert len(eventos) == 1
    payload = eventos[0]["payload"]
    assert payload["id"] == _body(response)["data"]["id"]
    assert payload["productId"] == product_id
    assert payload["userId"] == "usr_comprador"
    assert payload["calificacion"] == 5
    assert payload["total"] == 1


# Caso 2: sin compra ---------------------------------------------------------
def test_resena_sin_compra_devuelve_403(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _producto(client, create_product)

    response = _publicar_resena(client, product_id)

    assert response.status_code == 403
    data = _body(response)["data"]
    assert data["codigo"] == "REVIEW_PURCHASE_REQUIRED"
    assert data["regla"] == "COMU-04"
    assert client.get(f"{REVIEWS_URL}/{product_id}/rating").json()["data"]["total"] == 0


# Caso 3: reseña duplicada ---------------------------------------------------
def test_resena_duplicada_devuelve_409(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _producto(client, create_product)
    _licencia(client, product_id)
    assert _publicar_resena(client, product_id).status_code == 201

    respuesta = _publicar_resena(client, product_id, texto="Otra reseña del mismo usuario.")

    assert respuesta.status_code == 409
    assert _body(respuesta)["data"]["codigo"] == "REVIEW_DUPLICATE"
    assert _body(respuesta)["data"]["regla"] == "COMU-03"
    assert client.get(f"{REVIEWS_URL}/{product_id}/reviews").json()["data"]["total"] == 1


# Caso 4: calificación inválida ---------------------------------------------
def test_calificacion_fuera_de_rango_devuelve_400(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _producto(client, create_product)
    _licencia(client, product_id)

    respuesta = _publicar_resena(client, product_id, calificacion=6)

    assert respuesta.status_code == 400
    data = _body(respuesta)["data"]
    assert data["codigo"] == "REVIEW_RATING_INVALID"
    assert data["regla"] == "COMU-01"


def test_texto_fuera_de_longitud_devuelve_400(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _producto(client, create_product)
    _licencia(client, product_id)

    respuesta = _publicar_resena(client, product_id, texto="corto")

    assert respuesta.status_code == 400
    data = _body(respuesta)["data"]
    assert data["codigo"] == "REVIEW_TEXT_INVALID"
    assert data["regla"] == "COMU-02"


# Caso 5: consulta de promedio ----------------------------------------------
def test_consulta_de_promedio_y_distribucion(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _producto(client, create_product)
    _licencia(client, product_id)
    _licencia(client, product_id, "usr_comprador_2")
    assert _publicar_resena(client, product_id, calificacion=5).status_code == 201
    segunda = client.post(
        f"{REVIEWS_URL}/{product_id}/reviews",
        json={"calificacion": 3, "texto": "Buena calidad, entrega mejorable."},
        headers=OTRO_CONSUMIDOR,
    )
    assert segunda.status_code == 201

    respuesta = client.get(f"{REVIEWS_URL}/{product_id}/rating")

    assert respuesta.status_code == 200
    assert _body(respuesta)["data"] == {
        "promedio": 4.0,
        "total": 2,
        "distribucion": {"1": 0, "2": 0, "3": 1, "4": 0, "5": 1},
    }


def test_consultar_resenas_visibles_paginadas_y_sanitizadas(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _producto(client, create_product)
    _licencia(client, product_id)
    publicada = _publicar_resena(
        client, product_id, texto="<p>Excelente <b>calidad</b> y entrega inmediata.</p>"
    )
    assert publicada.status_code == 201
    review_id = _body(publicada)["data"]["id"]

    respuesta = client.get(
        f"{REVIEWS_URL}/{product_id}/reviews", params={"pagina": 1, "tamanioPagina": 1}
    )

    assert respuesta.status_code == 200
    data = _body(respuesta)["data"]
    assert data["total"] == 1
    assert data["pagina"] == 1
    assert data["tamanioPagina"] == 1
    assert data["items"][0]["id"] == review_id
    assert data["items"][0]["texto"] == "Excelente calidad y entrega inmediata."

    client.app.state.review_service.hide_review(product_id, review_id)
    assert client.get(f"{REVIEWS_URL}/{product_id}/reviews").json()["data"]["items"] == []
    assert client.get(f"{REVIEWS_URL}/{product_id}/rating").json()["data"]["total"] == 0


def test_flags_comu_03_y_04_pueden_desactivarse(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _producto(client, create_product)
    service = client.app.state.review_service
    service.settings = replace(
        service.settings,
        community_require_purchase=False,
        community_unique_review=False,
    )

    primera = _publicar_resena(client, product_id)
    segunda = _publicar_resena(client, product_id, texto="Muy buena compra y entrega.")

    assert primera.status_code == 201
    assert segunda.status_code == 201
    assert client.get(f"{REVIEWS_URL}/{product_id}/rating").json()["data"]["total"] == 2


def test_producto_inexistente_devuelve_404(client: TestClient):
    respuesta = client.post(
        f"{REVIEWS_URL}/prod_999/reviews", json=RESENA, headers=CONSUMIDOR
    )
    assert respuesta.status_code == 404
    assert _body(respuesta)["data"]["codigo"] == "PRODUCT_NOT_FOUND"
