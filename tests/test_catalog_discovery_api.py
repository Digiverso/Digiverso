"""Pruebas de aceptación de HU-10: búsqueda, filtros, vitrina y detalle."""

from __future__ import annotations

from typing import Any, Callable

from fastapi.testclient import TestClient

from tests.conftest import CATEGORIES_URL, PRODUCTS_URL

SHOWCASE_URL = "/api/v1/catalog/showcase"
PRODUCTOR = {"X-Actor-Id": "usr_010", "X-Actor-Roles": "productor"}
VISITANTE = {"X-Actor-Id": "usr_visitante", "X-Actor-Roles": "visitante"}
CONSUMIDOR = {"X-Actor-Id": "usr_comprador", "X-Actor-Roles": "consumidor"}


def _body(response) -> dict[str, Any]:
    return response.json()


def _categoria(client: TestClient, nombre: str) -> str:
    response = client.post(CATEGORIES_URL, json={"nombre": nombre})
    assert response.status_code == 201
    return _body(response)["data"]["id"]


def _publicar(
    client: TestClient,
    create_product: Callable[..., Any],
    *,
    categoria_id: str,
    **cambios: object,
) -> str:
    creado = create_product(
        headers=PRODUCTOR, categoria_id=categoria_id, **cambios
    )
    assert creado.status_code == 201
    product_id = _body(creado)["data"]["id"]
    assert client.patch(
        f"{PRODUCTS_URL}/{product_id}/archive", headers=PRODUCTOR
    ).status_code == 200
    publicado = client.patch(
        f"{PRODUCTS_URL}/{product_id}/reactivate", headers=PRODUCTOR
    )
    assert publicado.status_code == 200
    assert _body(publicado)["data"]["estado"] == "publicado"
    return product_id


# Caso 1: búsqueda por texto -------------------------------------------------
def test_busqueda_devuelve_solo_publicados_y_campos_publicos(
    client: TestClient, create_product: Callable[..., Any]
):
    categoria_id = _categoria(client, "Ilustración")
    publicado = _publicar(
        client,
        create_product,
        categoria_id=categoria_id,
        nombre="Pack de ilustraciones vectoriales",
    )
    borrador = _body(
        create_product(
            headers=PRODUCTOR,
            categoria_id=categoria_id,
            nombre="Ilustraciones sin publicar",
        )
    )["data"]["id"]

    response = client.get(PRODUCTS_URL, params={"q": "ilustracion"})

    assert response.status_code == 200
    body = _body(response)
    assert body["message"] == "Búsqueda realizada correctamente."
    assert body["success"] is True
    data = body["data"]
    assert set(data) == {"items", "total", "pagina", "tamanioPagina"}
    assert data["total"] == 1
    assert data["pagina"] == 1
    assert data["tamanioPagina"] == 20
    item = data["items"][0]
    assert item["id"] == publicado
    assert item["nombre"] == "Pack de ilustraciones vectoriales"
    assert {"id", "nombre", "precio", "autor", "categoria", "calificacion", "miniatura"} <= set(item)
    assert item["autor"] == "Autor Digiverso"
    assert item["categoria"] == "Ilustración"
    assert item["miniatura"].startswith("https://cdn.test/")
    assert "autorId" not in item
    assert borrador not in [producto["id"] for producto in data["items"]]


def test_indice_con_sinonimos_y_tolerancia_a_errores(
    client: TestClient, create_product: Callable[..., Any]
):
    categoria_id = _categoria(client, "Arte digital")
    publicado = _publicar(
        client,
        create_product,
        categoria_id=categoria_id,
        nombre="Pack de ilustraciones digitales",
    )

    por_sinonimo = client.get(PRODUCTS_URL, params={"q": "dibujo"})
    por_typo = client.get(PRODUCTS_URL, params={"q": "ilustrasion"})

    assert por_sinonimo.status_code == 200
    assert por_typo.status_code == 200
    assert [item["id"] for item in _body(por_sinonimo)["data"]["items"]] == [publicado]
    assert [item["id"] for item in _body(por_typo)["data"]["items"]] == [publicado]


# Caso 2: filtro por edad ----------------------------------------------------
def test_filtro_por_edad_devuelve_solo_productos_compatibles(
    client: TestClient, create_product: Callable[..., Any]
):
    categoria_id = _categoria(client, "Educación")
    infantil = _publicar(
        client,
        create_product,
        categoria_id=categoria_id,
        nombre="Cuentos para menores",
        edadMinima=0,
        edadMaxima=10,
    )
    adolescente = _publicar(
        client,
        create_product,
        categoria_id=categoria_id,
        nombre="Taller para adolescentes",
        edadMinima=12,
        edadMaxima=18,
    )

    respuesta = client.get(PRODUCTS_URL, params={"edad": 12})

    assert respuesta.status_code == 200
    assert [item["id"] for item in _body(respuesta)["data"]["items"]] == [adolescente]
    assert infantil not in [item["id"] for item in _body(respuesta)["data"]["items"]]
    assert [item["id"] for item in _body(client.get(PRODUCTS_URL, params={"edad": 5}))["data"]["items"]] == [infantil]


def test_filtros_se_combinan_con_and_y_orden_es_permitido(
    client: TestClient, create_product: Callable[..., Any]
):
    categoria_a = _categoria(client, "Categoría A")
    categoria_b = _categoria(client, "Categoría B")
    barato = _publicar(
        client,
        create_product,
        categoria_id=categoria_a,
        nombre="Pack económico",
        precio=40000,
    )
    caro = _publicar(
        client,
        create_product,
        categoria_id=categoria_a,
        nombre="Pack premium",
        precio=90000,
    )
    otra_categoria = _publicar(
        client,
        create_product,
        categoria_id=categoria_b,
        nombre="Pack de otra categoría",
        precio=45000,
    )

    combinado = client.get(
        PRODUCTS_URL,
        params={
            "categoria": categoria_a,
            "precioMin": 40000,
            "precioMax": 50000,
            "orden": "precio_desc",
        },
    )
    ordenado = client.get(PRODUCTS_URL, params={"orden": "precio_desc"})

    assert combinado.status_code == 200
    assert [item["id"] for item in _body(combinado)["data"]["items"]] == [barato]
    ids_ordenados = [item["id"] for item in _body(ordenado)["data"]["items"]]
    assert ids_ordenados.index(caro) < ids_ordenados.index(otra_categoria) < ids_ordenados.index(barato)
    assert ids_ordenados == sorted(
        ids_ordenados,
        key=lambda product_id: -next(
            item["precio"] for item in _body(ordenado)["data"]["items"] if item["id"] == product_id
        ),
    )


def test_filtros_invalidos_devuelven_422(
    client: TestClient, create_product: Callable[..., Any]
):
    categoria_id = _categoria(client, "Válida")

    casos = [
        {"edad": 100},
        {"precioMin": 100},
        {"precioMax": 3499},
        {"precioMin": 50000, "precioMax": 40000},
        {"categoria": "cat_999"},
        {"orden": "no_existe"},
        {"pagina": 0},
        {"tamanioPagina": 101},
        {"tamanioPagina": 0},
    ]
    for params in casos:
        respuesta = client.get(PRODUCTS_URL, params=params)
        assert respuesta.status_code == 422, params
        assert _body(respuesta)["success"] is False


# Caso 3: producto no publicado ----------------------------------------------
def test_detalle_de_no_publicado_es_404_para_visitante(
    client: TestClient, create_product: Callable[..., Any]
):
    categoria_id = _categoria(client, "Privado")
    borrador = _body(
        create_product(headers=PRODUCTOR, categoria_id=categoria_id)
    )["data"]["id"]

    respuesta = client.get(f"{PRODUCTS_URL}/{borrador}", headers=VISITANTE)

    assert respuesta.status_code == 404
    assert _body(respuesta)["success"] is False
    # El autor y el administrador sí pueden inspeccionar su propio borrador.
    assert client.get(f"{PRODUCTS_URL}/{borrador}", headers=PRODUCTOR).status_code == 200
    assert client.get(f"{PRODUCTS_URL}/{borrador}").status_code == 200


def test_detalle_publicado_incluye_medios_edad_y_oculta_datos_privados(
    client: TestClient, create_product: Callable[..., Any]
):
    categoria_id = _categoria(client, "Detalle público")
    publicado = _publicar(
        client,
        create_product,
        categoria_id=categoria_id,
        descripcion="Descripción completa del producto.",
        edadMinima=6,
        edadMaxima=12,
    )

    respuesta = client.get(f"{PRODUCTS_URL}/{publicado}", headers=VISITANTE)

    assert respuesta.status_code == 200
    data = _body(respuesta)["data"]
    assert data["descripcion"] == "Descripción completa del producto."
    assert data["edadMinima"] == 6
    assert data["edadMaxima"] == 12
    assert data["medios"][0]["url"].startswith("https://cdn.test/")
    assert data["autor"] == "Autor Digiverso"
    assert data["categoria"] == "Detalle público"
    assert data["licencia"] is None
    assert data["autorId"] is None
    assert data["licenciasActivas"] == 0


def test_licencia_vigente_da_acceso_a_producto_no_publicado(
    client: TestClient, create_product: Callable[..., Any], product_service
):
    categoria_id = _categoria(client, "Con licencia")
    borrador = _body(
        create_product(headers=PRODUCTOR, categoria_id=categoria_id)
    )["data"]["id"]
    product_service.attach_license(borrador, actor_id="usr_comprador")

    respuesta = client.get(f"{PRODUCTS_URL}/{borrador}", headers=CONSUMIDOR)

    assert respuesta.status_code == 200
    licencia = _body(respuesta)["data"]["licencia"]
    assert licencia["actorId"] == "usr_comprador"
    assert licencia["tipo"] == "estandar"
    assert licencia["vigente"] is True
    assert _body(respuesta)["data"]["autorId"] is None
    assert client.get(f"{PRODUCTS_URL}/{borrador}", headers=VISITANTE).status_code == 404


# Caso 4: vitrina por categoría ----------------------------------------------
def test_showcase_agrupa_publicados_y_se_invalida_al_archivar(
    client: TestClient,
    create_product: Callable[..., Any],
    product_service,
    showcase_cache,
):
    categoria_a = _categoria(client, "Ilustración")
    categoria_b = _categoria(client, "Música")
    primero = _publicar(client, create_product, categoria_id=categoria_a, nombre="Ilustración uno")
    segundo = _publicar(client, create_product, categoria_id=categoria_a, nombre="Ilustración dos")
    tercero = _publicar(client, create_product, categoria_id=categoria_b, nombre="Pista musical")
    _body(create_product(headers=PRODUCTOR, categoria_id=categoria_a, nombre="No publicado"))

    respuesta = client.get(SHOWCASE_URL)

    assert respuesta.status_code == 200
    data = _body(respuesta)["data"]
    assert data["total"] == 3
    assert len(data["categorias"]) == 2
    grupos = {grupo["nombre"]: grupo for grupo in data["categorias"]}
    assert {item["id"] for item in grupos["Ilustración"]["productos"]} == {primero, segundo}
    assert grupos["Ilustración"]["total"] == 2
    assert [item["id"] for item in grupos["Música"]["productos"]] == [tercero]
    assert showcase_cache.get(categoria_a) is not None

    assert client.patch(
        f"{PRODUCTS_URL}/{primero}/archive", headers=PRODUCTOR
    ).status_code == 200
    assert showcase_cache.get(categoria_a) is None
    despues = _body(client.get(SHOWCASE_URL))["data"]
    assert despues["total"] == 2
    ids_visibles = {
        item["id"]
        for grupo in despues["categorias"]
        for item in grupo["productos"]
    }
    assert primero not in ids_visibles
    assert segundo in ids_visibles
    assert tercero in ids_visibles


# Caso 5: paginación ---------------------------------------------------------
def test_paginacion_tiene_total_y_orden_estable(
    client: TestClient, create_product: Callable[..., Any]
):
    categoria_id = _categoria(client, "Paginación")
    ids = [
        _publicar(
            client,
            create_product,
            categoria_id=categoria_id,
            nombre=f"Producto paginado {numero:02d}",
        )
        for numero in range(25)
    ]

    pagina_1 = client.get(PRODUCTS_URL, params={"pagina": 1, "tamanioPagina": 20})
    pagina_2 = client.get(PRODUCTS_URL, params={"pagina": 2, "tamanioPagina": 20})
    repetida = client.get(PRODUCTS_URL, params={"pagina": 2, "tamanioPagina": 20})

    assert pagina_1.status_code == pagina_2.status_code == 200
    primera = _body(pagina_1)["data"]
    segunda = _body(pagina_2)["data"]
    assert (primera["total"], segunda["total"]) == (25, 25)
    assert len(primera["items"]) == 20
    assert len(segunda["items"]) == 5
    assert segunda["pagina"] == 2
    assert segunda["tamanioPagina"] == 20
    ids_primera = {item["id"] for item in primera["items"]}
    ids_segunda = {item["id"] for item in segunda["items"]}
    assert ids_primera.isdisjoint(ids_segunda)
    assert ids_primera | ids_segunda == set(ids)
    assert [item["id"] for item in segunda["items"]] == [
        item["id"] for item in _body(repetida)["data"]["items"]
    ]
    assert _body(client.get(PRODUCTS_URL, params={"pagina": 3, "tamanioPagina": 20}))["data"]["items"] == []
