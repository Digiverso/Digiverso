"""Pruebas de aceptación de HU-07 sobre la API HTTP."""

from __future__ import annotations

from typing import Any, Callable

from fastapi.testclient import TestClient

from tests.conftest import CATEGORIES_URL


def _body(response) -> dict[str, Any]:
    return response.json()


def _id(response) -> str:
    return _body(response)["data"]["id"]


class FakeCache:
    """Caché espía que cuenta invalidaciones sin alterar el comportamiento."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.invalidations = 0

    def get(self):
        return self.inner.get()

    def set(self, tree) -> None:
        self.inner.set(tree)

    def invalidate(self) -> None:
        self.invalidations += 1
        self.inner.invalidate()


# Caso 1 --------------------------------------------------------------------
def test_crear_categoria_devuelve_201_y_sobre_estandar(create_category: Callable[..., Any]):
    response = create_category("Ilustración digital", descripcion="Obras digitales", orden=2)

    assert response.status_code == 201
    body = _body(response)
    assert body["success"] is True
    assert body["message"] == "Categoría creada correctamente."
    data = body["data"]
    assert data["id"] == "cat_001"
    assert data["nombre"] == "Ilustración digital"
    assert data["padreId"] is None
    assert data["estado"] == "activa"
    assert data["orden"] == 2
    assert data["hijos"] == []


def test_crear_subcategoria_asigna_padre(create_category: Callable[..., Any]):
    root = create_category("Arte")
    child = create_category("Pintura", padre_id=_id(root))

    assert child.status_code == 201
    assert _body(child)["data"]["padreId"] == _id(root)


# Caso 2 --------------------------------------------------------------------
def test_nombre_duplicado_ignora_mayusculas_y_tildes(create_category: Callable[..., Any]):
    create_category("Ilustración digital")
    duplicate = create_category("ilustracion DIGITAL")

    assert duplicate.status_code == 409
    body = _body(duplicate)
    assert body["success"] is False
    assert body["data"]["nombre"] == "ilustracion DIGITAL"


def test_mismo_nombre_bajo_distinto_padre_es_valido(create_category: Callable[..., Any]):
    first_root = _id(create_category("Arte"))
    second_root = _id(create_category("Diseño"))

    assert create_category("Grabado", padre_id=first_root).status_code == 201
    assert create_category("Grabado", padre_id=second_root).status_code == 201


def test_longitud_cat_17(create_category: Callable[..., Any]):
    assert create_category("a").status_code == 422
    assert create_category("x" * 81).status_code == 422
    assert _body(create_category("a"))["success"] is False


# Caso 3 --------------------------------------------------------------------
def test_no_se_permite_ciclo_al_mover_padre_bajo_hijo(
    client: TestClient, create_category: Callable[..., Any]
):
    root = _id(create_category("Arte"))
    child = _id(create_category("Pintura", padre_id=root))
    _ = _id(create_category("Óleo", padre_id=child))

    response = client.patch(
        f"{CATEGORIES_URL}/{root}", json={"padreId": child}
    )

    assert response.status_code == 400
    assert _body(response)["success"] is False
    before = _body(client.get(CATEGORIES_URL))["data"]
    assert [node["id"] for node in before] == [root]


def test_no_se_permite_mover_una_categoria_bajo_si_misma(
    client: TestClient, create_category: Callable[..., Any]
):
    root = _id(create_category("Arte"))
    response = client.patch(f"{CATEGORIES_URL}/{root}", json={"padreId": root})

    assert response.status_code == 400


def test_padre_inexistente(create_category: Callable[..., Any]):
    response = create_category("Pintura", padre_id="cat_999")

    assert response.status_code == 400
    assert "no existe" in _body(response)["message"]


# FUN-18 --------------------------------------------------------------------
def test_patch_actualiza_campos_y_mueve_subarbol(
    client: TestClient, create_category: Callable[..., Any], category_service
):
    first_root = _id(create_category("Arte"))
    second_root = _id(create_category("Diseño"))
    child = _id(create_category("Pintura", padre_id=first_root))
    grandchild = _id(create_category("Óleo", padre_id=child))

    response = client.patch(
        f"{CATEGORIES_URL}/{child}",
        json={
            "nombre": "Pintura clásica",
            "descripcion": "Técnicas tradicionales",
            "padreId": second_root,
            "orden": 3,
        },
    )

    assert response.status_code == 200
    data = _body(response)["data"]
    assert data["nombre"] == "Pintura clásica"
    assert data["padreId"] == second_root
    assert data["orden"] == 3

    assert category_service.repository.get(grandchild).ruta == (
        f"/{second_root}/{child}/{grandchild}/"
    )

    tree = _body(client.get(CATEGORIES_URL))["data"]
    diseno = next(node for node in tree if node["id"] == second_root)
    assert diseno["hijos"][0]["id"] == child
    assert diseno["hijos"][0]["hijos"][0]["id"] == grandchild


# Caso 4 --------------------------------------------------------------------
def test_desactivar_con_productos_activos_devuelve_409(
    client: TestClient, create_category: Callable[..., Any], category_service
):
    category_id = _id(create_category("Fotografía"))
    category_service.repository.add_product("prod_100", category_id)

    response = client.delete(f"{CATEGORIES_URL}/{category_id}")

    assert response.status_code == 409
    assert _body(response)["data"]["productosActivos"] == 1
    assert category_service.repository.get(category_id).estado == "activa"


def test_producto_activo_en_descendiente_tambien_bloquea(
    client: TestClient, create_category: Callable[..., Any], category_service
):
    root = _id(create_category("Arte"))
    child = _id(create_category("Fotografía", padre_id=root))
    category_service.repository.add_product("prod_101", child)

    response = client.delete(f"{CATEGORIES_URL}/{root}")

    assert response.status_code == 409


def test_desactivar_sin_productos_es_logico_y_se_audita(
    client: TestClient, create_category: Callable[..., Any], category_service
):
    headers = {"X-Actor-Id": "usr_002", "X-Actor-Roles": "administrador"}
    category_id = _id(create_category("Escultura", headers=headers))

    response = client.delete(f"{CATEGORIES_URL}/{category_id}", headers=headers)

    assert response.status_code == 200
    data = _body(response)["data"]
    assert data["estado"] == "inactiva"
    assert category_service.repository.get(category_id) is not None
    assert all(node["id"] != category_id for node in _body(client.get(CATEGORIES_URL))["data"])

    events = category_service.audit_repository.list_for_entity(category_id)
    assert [event["accion"] for event in events] == ["crear", "desactivar"]
    assert {event["actorId"] for event in events} == {"usr_002"}


# Caso 5 --------------------------------------------------------------------
def test_consultar_arbol_anidado_y_solo_activo(
    client: TestClient, create_category: Callable[..., Any]
):
    root = _id(create_category("Arte"))
    child = _id(create_category("Pintura", padre_id=root, orden=1))
    grandchild = _id(create_category("Óleo", padre_id=child))
    inactive = _id(create_category("Grabado", padre_id=root, orden=2))
    client.delete(f"{CATEGORIES_URL}/{inactive}")

    response = client.get(CATEGORIES_URL)

    assert response.status_code == 200
    body = _body(response)
    assert body["success"] is True
    assert body["message"] == "Árbol de categorías consultado correctamente."
    tree = body["data"]
    assert [node["id"] for node in tree] == [root]
    assert [node["id"] for node in tree[0]["hijos"]] == [child]
    assert tree[0]["hijos"][0]["hijos"][0]["id"] == grandchild


def test_arbol_esta_ordenado_por_orden(create_category: Callable[..., Any], client: TestClient):
    root = _id(create_category("Arte"))
    second = _id(create_category("Pintura", padre_id=root, orden=2))
    first = _id(create_category("Dibujo", padre_id=root, orden=1))

    children = _body(client.get(CATEGORIES_URL))["data"][0]["hijos"]
    assert [node["id"] for node in children] == [first, second]


# Cache, permisos y errores --------------------------------------------------
def test_cache_se_invalida_en_cada_escritura(
    client: TestClient, create_category: Callable[..., Any], category_service
):
    spy = FakeCache(category_service.cache)
    category_service.cache = spy

    client.get(CATEGORIES_URL)
    assert spy.invalidations == 0

    category_id = _id(create_category("Arte"))
    client.patch(f"{CATEGORIES_URL}/{category_id}", json={"descripcion": "Categoría raíz"})
    client.delete(f"{CATEGORIES_URL}/{category_id}")

    assert spy.invalidations == 3
    assert _body(client.get(CATEGORIES_URL))["data"] == []


def test_escritura_sin_permiso_devuelve_403(client: TestClient):
    response = client.post(
        CATEGORIES_URL,
        json={"nombre": "Arte"},
        headers={"X-Actor-Id": "usr_003", "X-Actor-Roles": "consumidor"},
    )

    assert response.status_code == 403
    assert _body(response)["success"] is False
    assert _body(client.get(CATEGORIES_URL))["data"] == []


def test_duplicado_al_renombar_devuelve_409(
    client: TestClient, create_category: Callable[..., Any]
):
    create_category("Arte")
    second = _id(create_category("Diseño"))

    response = client.patch(f"{CATEGORIES_URL}/{second}", json={"nombre": " arte "})

    assert response.status_code == 409
    assert any(
        node["nombre"] == "Arte" for node in _body(client.get(CATEGORIES_URL))["data"]
    )


def test_campos_desconocidos_son_rechazados(client: TestClient):
    response = client.post(
        CATEGORIES_URL, json={"nombre": "Arte", "campoExtra": 1}
    )

    assert response.status_code == 422
