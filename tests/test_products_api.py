"""Pruebas de aceptación de HU-08 sobre la API HTTP."""

from __future__ import annotations

from typing import Any, Callable

from fastapi.testclient import TestClient

from app.core.security import ActorTokenManager
from tests.conftest import CATEGORIES_URL, PRODUCTS_URL

PRODUCTOR = {"X-Actor-Id": "usr_010", "X-Actor-Roles": "productor"}
OTRO_PRODUCTOR = {"X-Actor-Id": "usr_011", "X-Actor-Roles": "productor"}


def _body(response) -> dict[str, Any]:
    return response.json()


def _id(response) -> str:
    return _body(response)["data"]["id"]


def _publicar(client: TestClient, create_product: Callable[..., Any]) -> str:
    """Lleva un producto a ``publicado`` usando solo los endpoints de HU-08."""

    product_id = _id(create_product(headers=PRODUCTOR))
    assert client.patch(
        f"{PRODUCTS_URL}/{product_id}/archive", headers=PRODUCTOR
    ).status_code == 200
    response = client.patch(
        f"{PRODUCTS_URL}/{product_id}/reactivate", headers=PRODUCTOR
    )
    assert response.status_code == 200
    assert _body(response)["data"]["estado"] == "publicado"
    return product_id


# Caso 1 --------------------------------------------------------------------
def test_crear_producto_valido_devuelve_201_en_borrador(
    create_product: Callable[..., Any]
):
    response = create_product(headers=PRODUCTOR)

    assert response.status_code == 201
    body = _body(response)
    assert body["success"] is True
    assert body["message"] == "Producto creado en borrador."
    data = body["data"]
    assert data["id"] == "prod_001"
    assert data["nombre"] == "Pack de ilustraciones"
    assert data["precio"] == 45000
    assert data["moneda"] == "COP"
    assert data["edadMinima"] == 0
    assert data["edadMaxima"] == 99
    assert data["estado"] == "borrador"
    assert data["autorId"] == "usr_010"
    assert len(data["categorias"]) == 1
    assert data["medios"][0]["tipo"] == "imagen"
    assert data["licenciasActivas"] == 0


def test_autor_del_cuerpo_se_ignora(create_product: Callable[..., Any]):
    response = create_product(headers=PRODUCTOR, autorId="usr_999")

    assert response.status_code == 201
    assert _body(response)["data"]["autorId"] == "usr_010"


def test_autor_se_toma_de_token_firmado(client: TestClient):
    category = client.post(CATEGORIES_URL, json={"nombre": "Ilustración"})
    categoria_id = _body(category)["data"]["id"]
    token = ActorTokenManager("cambia-este-valor-en-produccion").issue(
        "usr_020", ("productor",)
    )
    response = client.post(
        PRODUCTS_URL,
        json={
            "nombre": "Pack tokenizado",
            "descripcion": "Producto creado con token firmado.",
            "precio": 45000,
            "categorias": [categoria_id],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert _body(response)["data"]["autorId"] == "usr_020"


def test_token_invalido_devuelve_403(client: TestClient):
    response = client.post(
        PRODUCTS_URL,
        json={
            "nombre": "Pack",
            "descripcion": "Producto de prueba.",
            "precio": 45000,
            "categorias": ["cat_001"],
        },
        headers={"Authorization": "Bearer token.invalido"},
    )
    assert response.status_code == 403


# Caso 2 --------------------------------------------------------------------
def test_precio_bajo_el_minimo_devuelve_422_y_no_crea(
    client: TestClient, create_product: Callable[..., Any]
):
    response = create_product(headers=PRODUCTOR, precio=3000)

    assert response.status_code == 422
    assert _body(response)["success"] is False
    assert "CAT-01" in _body(response)["message"]
    assert client.get(f"{PRODUCTS_URL}/prod_001").status_code == 404


def test_validaciones_de_dominio_cat_03_11_12_13(create_product: Callable[..., Any]):
    assert create_product(headers=PRODUCTOR, precio=3499).status_code == 422
    assert create_product(headers=PRODUCTOR, edadMinima=90, edadMaxima=18).status_code == 422
    assert create_product(headers=PRODUCTOR, edadMaxima=100).status_code == 422
    assert create_product(headers=PRODUCTOR, nombre="a").status_code == 422
    assert create_product(headers=PRODUCTOR, descripcion="").status_code == 422
    assert create_product(headers=PRODUCTOR, categorias=[]).status_code == 422
    assert create_product(headers=PRODUCTOR, categorias=["cat_999"]).status_code == 422
    assert create_product(headers=PRODUCTOR, moneda="USD").status_code == 422


# Caso 3 --------------------------------------------------------------------
def test_editar_producto_ajeno_devuelve_403(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _id(create_product(headers=PRODUCTOR))

    response = client.patch(
        f"{PRODUCTS_URL}/{product_id}",
        json={"precio": 50000},
        headers=OTRO_PRODUCTOR,
    )

    assert response.status_code == 403
    assert _body(response)["data"]["actorId"] == "usr_011"
    assert _body(client.get(f"{PRODUCTS_URL}/{product_id}"))["data"]["precio"] == 45000


def test_editar_producto_propio_actualiza_campos(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _id(create_product(headers=PRODUCTOR))

    response = client.patch(
        f"{PRODUCTS_URL}/{product_id}",
        json={"precio": 50000, "autorId": "usr_999"},
        headers=PRODUCTOR,
    )

    assert response.status_code == 200
    data = _body(response)["data"]
    assert data["precio"] == 50000
    assert data["autorId"] == "usr_010"


# Caso 4 --------------------------------------------------------------------
def test_enviar_sin_imagenes_devuelve_422_y_sigue_en_borrador(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _id(create_product(headers=PRODUCTOR, medios=[]))

    response = client.post(
        f"{PRODUCTS_URL}/{product_id}/submit-review", headers=PRODUCTOR
    )

    assert response.status_code == 422
    assert "CAT-09" in _body(response)["message"]
    assert _body(client.get(f"{PRODUCTS_URL}/{product_id}"))["data"]["estado"] == "borrador"


def test_enviar_con_imagenes_pasa_a_revision_y_devuelve_fecha(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _id(create_product(headers=PRODUCTOR))

    response = client.post(
        f"{PRODUCTS_URL}/{product_id}/submit-review", headers=PRODUCTOR
    )

    assert response.status_code == 200
    data = _body(response)["data"]
    assert data["estado"] == "en_revision"
    assert data["estadoAnterior"] == "borrador"
    assert data["transicion"] == "enviar a revisión"
    assert data["fecha"] is not None


def test_medios_como_url_simple_cuentan_como_imagen(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _id(
        create_product(headers=PRODUCTOR, medios=["https://cdn.test/dos.webp"])
    )

    response = client.post(
        f"{PRODUCTS_URL}/{product_id}/submit-review", headers=PRODUCTOR
    )

    assert response.status_code == 200
    assert _body(response)["data"]["estado"] == "en_revision"


# Caso 5 --------------------------------------------------------------------
def test_archivar_con_licencias_las_conserva_y_retira_de_la_vitrina(
    client: TestClient, create_product: Callable[..., Any], product_service
):
    product_id = _publicar(client, create_product)
    product_service.attach_license(product_id, tipo="estandar")
    assert len(_body(client.get(PRODUCTS_URL))["data"]["items"]) == 1

    response = client.patch(
        f"{PRODUCTS_URL}/{product_id}/archive", headers=PRODUCTOR
    )

    assert response.status_code == 200
    data = _body(response)["data"]
    assert data["estado"] == "archivado"
    assert data["estadoAnterior"] == "publicado"
    assert data["fecha"] is not None
    assert data["licenciasActivas"] == 1
    assert [lic["vigente"] for lic in product_service.repository.list_licenses(product_id)] == [True]
    assert _body(client.get(PRODUCTS_URL))["data"]["items"] == []


# Caso 6 --------------------------------------------------------------------
def test_reactivar_con_cambios_envia_a_revision(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _publicar(client, create_product)
    client.patch(f"{PRODUCTS_URL}/{product_id}/archive", headers=PRODUCTOR)
    cambio = client.patch(
        f"{PRODUCTS_URL}/{product_id}",
        json={"precio": 60000},
        headers=PRODUCTOR,
    )
    assert cambio.status_code == 200

    response = client.patch(
        f"{PRODUCTS_URL}/{product_id}/reactivate", headers=PRODUCTOR
    )

    assert response.status_code == 200
    data = _body(response)["data"]
    assert data["estado"] == "en_revision"
    assert data["estadoAnterior"] == "archivado"
    assert data["fecha"] is not None


def test_reactivar_sin_cambios_publica(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _id(create_product(headers=PRODUCTOR))
    client.patch(f"{PRODUCTS_URL}/{product_id}/archive", headers=PRODUCTOR)

    response = client.patch(
        f"{PRODUCTS_URL}/{product_id}/reactivate", headers=PRODUCTOR
    )

    assert response.status_code == 200
    assert _body(response)["data"]["estado"] == "publicado"
    assert _body(response)["data"]["licenciasActivas"] == 0


# Transiciones inválidas -----------------------------------------------------
def test_transiciones_invalidas_devuelven_409(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _id(create_product(headers=PRODUCTOR))

    assert (
        client.patch(
            f"{PRODUCTS_URL}/{product_id}/reactivate", headers=PRODUCTOR
        ).status_code
        == 409
    )

    client.post(f"{PRODUCTS_URL}/{product_id}/submit-review", headers=PRODUCTOR)
    assert (
        client.post(
            f"{PRODUCTS_URL}/{product_id}/submit-review", headers=PRODUCTOR
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"{PRODUCTS_URL}/{product_id}",
            json={"precio": 50000},
            headers=PRODUCTOR,
        ).status_code
        == 409
    )

    client.patch(f"{PRODUCTS_URL}/{product_id}/archive", headers=PRODUCTOR)
    assert (
        client.patch(
            f"{PRODUCTS_URL}/{product_id}/archive", headers=PRODUCTOR
        ).status_code
        == 409
    )


def test_campos_desconocidos_son_rechazados(create_product: Callable[..., Any]):
    assert create_product(headers=PRODUCTOR, campoExtra=1).status_code == 422


# Auditoría ------------------------------------------------------------------
def test_transiciones_se_auditan_con_actor_y_fecha(
    client: TestClient, create_product: Callable[..., Any], product_service
):
    product_id = _id(create_product(headers=PRODUCTOR))
    client.post(f"{PRODUCTS_URL}/{product_id}/submit-review", headers=PRODUCTOR)
    client.patch(f"{PRODUCTS_URL}/{product_id}/archive", headers=PRODUCTOR)
    client.patch(f"{PRODUCTS_URL}/{product_id}/reactivate", headers=PRODUCTOR)

    eventos = product_service.audit_repository.list_for_entity(
        product_id, entidad="producto"
    )

    assert [evento["accion"] for evento in eventos] == [
        "crear",
        "enviar_revision",
        "archivar",
        "reactivar",
    ]
    assert {evento["actorId"] for evento in eventos} == {"usr_010"}
    assert all(evento["fecha"] for evento in eventos)
    assert eventos[-1]["cambios"]["estadoAnterior"] == "archivado"
    assert eventos[-1]["cambios"]["estado"] == "publicado"
