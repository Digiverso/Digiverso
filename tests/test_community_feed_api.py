"""Pruebas de aceptación de HU-19: seguimiento, feed, intereses y recomendaciones."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi.testclient import TestClient

from app.domain.auth import AccountStatus, Role
from app.domain.community import CommunitySettings
from app.repository.auth_repository import auth_repository
from app.repository.categories import SQLiteCategoryRepository
from app.repository.community import SQLiteCommunityRepository
from app.repository.products import SQLiteProductRepository
from app.services.community import CommunityService
from tests.conftest import CATEGORIES_URL, PRODUCTS_URL

COMMUNITY_URL = "/api/v1/community"
CONSUMIDOR = {"X-Actor-Id": "usr_comprador", "X-Actor-Roles": "consumidor"}
PRODUCTOR = {"X-Actor-Id": "usr_001", "X-Actor-Roles": "productor"}


def _body(response) -> dict[str, Any]:
    return response.json()


def _cuenta(nombre: str) -> str:
    cuenta = auth_repository.crear_cuenta(
        nombre,
        f"{nombre.lower().replace(' ', '.')}@example.com",
        "hash",
        AccountStatus.ACTIVA,
        Role.PRODUCTOR,
        datetime.now(timezone.utc),
    )
    return cuenta.id


def _categoria(client: TestClient, nombre: str) -> str:
    response = client.post(CATEGORIES_URL, json={"nombre": nombre})
    assert response.status_code == 201
    return _body(response)["data"]["id"]


def _publicar(
    client: TestClient,
    create_product: Callable[..., Any],
    categoria_id: str,
    *,
    nombre: str,
    headers: dict[str, str] = PRODUCTOR,
) -> str:
    creado = create_product(
        headers=headers,
        categoria_id=categoria_id,
        nombre=nombre,
        descripcion=f"{nombre} en alta resolución para descargar.",
    )
    assert creado.status_code == 201
    producto_id = _body(creado)["data"]["id"]
    assert client.patch(
        f"{PRODUCTS_URL}/{producto_id}/archive", headers=headers
    ).status_code == 200
    publicado = client.patch(
        f"{PRODUCTS_URL}/{producto_id}/reactivate", headers=headers
    )
    assert publicado.status_code == 200
    assert _body(publicado)["data"]["estado"] == "publicado"
    return producto_id


def _seguir(client: TestClient, usuario_id: str, headers: dict[str, str] = CONSUMIDOR):
    return client.post(f"{COMMUNITY_URL}/users/{usuario_id}/follow", headers=headers)


def _reservar(client: TestClient, producto_id: str, usuario_id: str) -> None:
    repositorio = SQLiteProductRepository(client.app.state.database)
    repositorio.add_license(producto_id, actor_id=usuario_id)


def _configurar(
    client: TestClient, **cambios: object
) -> CommunityService:
    datos = client.app.state.database
    servicio = CommunityService(
        repository=SQLiteCommunityRepository(datos),
        product_repository=SQLiteProductRepository(datos),
        category_repository=SQLiteCategoryRepository(datos),
        account_provider=auth_repository.obtener_cuenta_por_id,
        cache=client.app.state.community_feed_cache,
        settings=replace(client.app.state.community_settings, **cambios),
    )
    client.app.state.community_service = servicio
    return servicio


# Caso 1: seguir productor ---------------------------------------------------
def test_seguir_productor_crea_relacion_y_actualiza_contadores(client: TestClient):
    productor_id = _cuenta("Ana Torres")

    respuesta = _seguir(client, productor_id)
    duplicada = _seguir(client, productor_id)

    assert respuesta.status_code == 201
    datos = _body(respuesta)["data"]
    assert datos["seguidoId"] == productor_id
    assert datos["totalSiguiendo"] == 1
    assert datos["totalSeguidores"] == 1
    assert duplicada.status_code == 409
    assert _body(duplicada)["data"]["codigo"] == "FOLLOW_DUPLICATE"


# Caso 2: auto-seguimiento ---------------------------------------------------
def test_auto_seguimiento_respondes_400_en_dominio(client: TestClient):
    respuesta = _seguir(client, "usr_comprador")

    assert respuesta.status_code == 400
    assert _body(respuesta)["data"]["codigo"] == "FOLLOW_SELF"


def test_usuario_inexistente_respondes_404(client: TestClient):
    respuesta = _seguir(client, "usr_inexistente")

    assert respuesta.status_code == 404
    assert _body(respuesta)["data"]["codigo"] == "USER_NOT_FOUND"


def test_limite_comu_05_respondes_409(client: TestClient):
    _configurar(client, max_following=1)
    primero = _cuenta("Ana Torres")
    segundo = _cuenta("Luis Ruiz")

    assert _seguir(client, primero).status_code == 201
    excedido = _seguir(client, segundo)

    assert excedido.status_code == 409
    assert _body(excedido)["data"]["regla"] == "COMU-05"
    assert _body(excedido)["data"]["limite"] == 1


# Caso 3: feed de seguidos ---------------------------------------------------
def test_feed_muestra_solo_publicados_de_seguidos_paginado(
    client: TestClient, create_product: Callable[..., Any]
):
    productor_id = _cuenta("Ana Torres")
    _cuenta("Luis Ruiz")
    categoria = _categoria(client, "Ilustración")
    publicado = _publicar(
        client, create_product, categoria, nombre="Pack de ilustraciones"
    )
    _publicar(
        client,
        create_product,
        categoria,
        nombre="Producto de otro autor",
        headers={"X-Actor-Id": "usr_002", "X-Actor-Roles": "productor"},
    )
    create_product(
        headers=PRODUCTOR,
        categoria_id=categoria,
        nombre="Borrador del seguido",
    )
    assert _seguir(client, productor_id).status_code == 201

    respuesta = client.get(f"{COMMUNITY_URL}/feed/following", headers=CONSUMIDOR)

    assert respuesta.status_code == 200
    cuerpo = _body(respuesta)
    assert cuerpo["message"] == "Feed consultado correctamente."
    assert cuerpo["success"] is True
    datos = cuerpo["data"]
    assert {"items", "total", "pagina"} <= set(datos)
    assert datos["total"] == 1
    assert datos["pagina"] == 1
    item = datos["items"][0]
    assert item["productId"] == publicado
    assert {"productId", "nombre", "autor", "precio", "fecha"} <= set(item)
    # La fixture de productos de catálogo no inyecta proveedor de nombre: el
    # autor persistido es el valor por defecto usado por HU-08/HU-10.
    assert item["autor"] == "Autor Digiverso"
    assert item["precio"] == 45000
    pagina_dos = client.get(
        f"{COMMUNITY_URL}/feed/following",
        params={"pagina": 2, "tamanioPagina": 1},
        headers=CONSUMIDOR,
    )
    assert _body(pagina_dos)["data"]["items"] == []


def test_feed_invalida_cache_al_publicar_y_al_dejar_de_seguir(
    client: TestClient, create_product: Callable[..., Any]
):
    productor_id = _cuenta("Ana Torres")
    categoria = _categoria(client, "Ilustración")
    _publicar(client, create_product, categoria, nombre="Primer pack")
    assert _seguir(client, productor_id).status_code == 201

    primera = client.get(f"{COMMUNITY_URL}/feed/following", headers=CONSUMIDOR)
    assert _body(primera)["data"]["total"] == 1
    _publicar(client, create_product, categoria, nombre="Segundo pack")

    segunda = client.get(f"{COMMUNITY_URL}/feed/following", headers=CONSUMIDOR)
    assert _body(segunda)["data"]["total"] == 2

    baja = client.delete(
        f"{COMMUNITY_URL}/users/{productor_id}/follow", headers=CONSUMIDOR
    )
    assert baja.status_code == 200
    assert _body(baja)["data"]["eliminado"] is True
    assert _body(baja)["data"]["totalSiguiendo"] == 0
    assert _body(baja)["data"]["totalSeguidores"] == 0
    tercera = client.get(f"{COMMUNITY_URL}/feed/following", headers=CONSUMIDOR)
    assert _body(tercera)["data"]["total"] == 0


def test_paginacion_fuera_de_rango_respondes_422(client: TestClient):
    respuesta = client.get(
        f"{COMMUNITY_URL}/feed/following",
        params={"pagina": 0},
        headers=CONSUMIDOR,
    )
    assert respuesta.status_code == 422
    assert _body(respuesta)["data"]["codigo"] == "COMMUNITY_QUERY_INVALID"


# Caso 4: intereses excedidos ------------------------------------------------
def test_intereses_validan_categorias_y_limite_comu_08(client: TestClient):
    primera = _categoria(client, "Ilustración")
    segunda = _categoria(client, "Educación")
    url = f"{COMMUNITY_URL}/me/interests"

    actualizados = client.put(
        url, json={"categorias": [primera, primera, segunda]}, headers=CONSUMIDOR
    )
    assert actualizados.status_code == 200
    assert _body(actualizados)["data"]["categorias"] == [primera, segunda]
    assert _body(actualizados)["data"]["total"] == 2

    inexistente = client.put(
        url, json={"categorias": ["cat_inexistente"]}, headers=CONSUMIDOR
    )
    assert inexistente.status_code == 400
    assert _body(inexistente)["data"]["codigo"] == "INTEREST_INVALID"

    _configurar(client, max_interests=1)
    excedido = client.put(
        url, json={"categorias": [primera, segunda]}, headers=CONSUMIDOR
    )
    assert excedido.status_code == 409
    assert _body(excedido)["data"]["regla"] == "COMU-08"


# Caso 5: recomendaciones ----------------------------------------------------
def test_recomendaciones_excluyen_comprados_y_propios(
    client: TestClient, create_product: Callable[..., Any]
):
    _cuenta("Ana Torres")
    interes = _categoria(client, "Ilustración")
    otro = _categoria(client, "Música")
    afines = _publicar(
        client, create_product, interes, nombre="Pack de ilustraciones"
    )
    comprado = _publicar(
        client, create_product, otro, nombre="Curso de piano"
    )
    propio = _publicar(
        client,
        create_product,
        interes,
        nombre="Producto propio del consumidor",
        headers=CONSUMIDOR,
    )
    _reservar(client, comprado, "usr_comprador")
    client.put(
        f"{COMMUNITY_URL}/me/interests",
        json={"categorias": [interes]},
        headers=CONSUMIDOR,
    )

    respuesta = client.get(f"{COMMUNITY_URL}/feed/recommended", headers=CONSUMIDOR)

    assert respuesta.status_code == 200
    datos = _body(respuesta)["data"]
    identificadores = [item["productId"] for item in datos["items"]]
    assert identificadores == [afines]
    assert comprado not in identificadores
    assert propio not in identificadores
    item = datos["items"][0]
    assert {"productId", "motivo", "puntuacion"} <= set(item)
    assert "intereses" in item["motivo"]
    assert item["puntuacion"] > 0
    assert datos["orden"] == "puntuacion_desc,fecha_desc,id_asc"


def test_recomendaciones_respetan_limite_comu_09(
    client: TestClient, create_product: Callable[..., Any]
):
    _cuenta("Ana Torres")
    categoria = _categoria(client, "Ilustración")
    primero = _publicar(client, create_product, categoria, nombre="Pack uno")
    segundo = _publicar(client, create_product, categoria, nombre="Pack dos")
    _configurar(client, max_recommendations=1)

    respuesta = client.get(f"{COMMUNITY_URL}/feed/recommended", headers=CONSUMIDOR)

    assert respuesta.status_code == 200
    datos = _body(respuesta)["data"]
    assert datos["limite"] == 1
    assert datos["total"] == 1
    assert [item["productId"] for item in datos["items"]] in (
        [primero],
        [segundo],
    )
