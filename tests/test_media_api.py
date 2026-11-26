"""Pruebas de aceptación de HU-09 sobre la API HTTP."""

from __future__ import annotations

import base64
from typing import Any, Callable

from fastapi.testclient import TestClient

from tests.conftest import CATEGORIES_URL, PRODUCTS_URL

PRODUCTOR = {"X-Actor-Id": "usr_010", "X-Actor-Roles": "productor"}
OTRO_PRODUCTOR = {"X-Actor-Id": "usr_011", "X-Actor-Roles": "productor"}

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/"
    "q842iQAAAABJRU5ErkJggg=="
)
GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 16


def _body(response) -> dict[str, Any]:
    return response.json()


def _crear(client: TestClient, create_product: Callable[..., Any], **cambios: object) -> str:
    cambios.setdefault("medios", [])
    response = create_product(headers=PRODUCTOR, **cambios)
    assert response.status_code == 201
    return _body(response)["data"]["id"]


def _subir(
    client: TestClient,
    product_id: str,
    *,
    nombre: str = "foto.png",
    contenido: bytes = PNG,
    mime: str = "image/png",
    campo: str = "archivo",
    headers: dict[str, str] | None = None,
):
    return client.post(
        f"{PRODUCTS_URL}/{product_id}/media",
        files={campo: (nombre, contenido, mime)},
        headers=headers or PRODUCTOR,
    )


# Caso 1 --------------------------------------------------------------------
def test_cargar_imagen_valida_devuelve_201_con_medio_asociado(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _crear(client, create_product)

    response = _subir(client, product_id)

    assert response.status_code == 201
    body = _body(response)
    assert body["success"] is True
    assert body["message"] == "Medio cargado correctamente."
    data = body["data"]
    assert data["id"] == "med_001"
    assert data["productoId"] == product_id
    assert data["tipo"] == "imagen"
    assert data["url"] == f"https://cdn.test/products/{product_id}/med_001.png"
    assert data["orden"] == 1
    assert data["estado"] == "activo"

    producto = _body(client.get(f"{PRODUCTS_URL}/{product_id}"))["data"]
    assert producto["medios"] == [
        {
            "id": "med_001",
            "tipo": "imagen",
            "url": data["url"],
            "orden": 1,
            "estado": "activo",
        }
    ]


def test_cargar_video_valido_y_campo_file_alternativo(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _crear(client, create_product)

    response = _subir(
        client,
        product_id,
        nombre="video.mp4",
        contenido=MP4,
        mime="video/mp4",
        campo="file",
    )

    assert response.status_code == 201
    assert _body(response)["data"]["tipo"] == "video"


# Caso 2 --------------------------------------------------------------------
def test_formato_no_permitido_devuelve_400(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _crear(client, create_product)

    response = _subir(client, product_id, nombre="anim.gif", contenido=GIF, mime="image/gif")

    assert response.status_code == 400
    assert _body(response)["success"] is False
    assert "CAT-05" in _body(response)["message"]
    assert _body(client.get(f"{PRODUCTS_URL}/{product_id}"))["data"]["medios"] == []


def test_extension_enganosa_devuelve_400(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _crear(client, create_product)

    response = _subir(client, product_id, nombre="foto.mp4", contenido=PNG, mime="image/png")

    assert response.status_code == 400


# Caso 3 --------------------------------------------------------------------
def test_archivo_demasiado_grande_devuelve_413(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _crear(client, create_product)
    grande = PNG + b"\x00" * (10 * 1024 * 1024)

    response = _subir(client, product_id, contenido=grande)

    assert response.status_code == 413
    assert "CAT-06" in _body(response)["message"]
    assert _body(response)["data"]["maximoBytes"] == 10 * 1024 * 1024


# Caso 4 --------------------------------------------------------------------
def test_eliminar_medio_ajeno_devuelve_403(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _crear(client, create_product)
    media_id = _body(_subir(client, product_id))["data"]["id"]

    response = client.delete(
        f"{PRODUCTS_URL}/{product_id}/media/{media_id}", headers=OTRO_PRODUCTOR
    )

    assert response.status_code == 403
    assert _body(response)["data"]["actorId"] == "usr_011"
    assert len(_body(client.get(f"{PRODUCTS_URL}/{product_id}"))["data"]["medios"]) == 1


def test_cargar_en_producto_ajeno_devuelve_403(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _crear(client, create_product)

    response = _subir(client, product_id, headers=OTRO_PRODUCTOR)

    assert response.status_code == 403


# Caso 5 --------------------------------------------------------------------
def test_superar_maximo_de_medios_devuelve_409(
    client: TestClient, create_product: Callable[..., Any]
):
    medios = [{"tipo": "imagen", "url": f"https://cdn.test/{indice}.webp"} for indice in range(10)]
    product_id = _crear(client, create_product, medios=medios)

    response = _subir(client, product_id)

    assert response.status_code == 409
    assert "CAT-10" in _body(response)["message"]
    assert _body(response)["data"]["maximo"] == 10


# Eliminación lógica y reordenamiento ---------------------------------------
def test_eliminar_medio_propio_reordena_restantes(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _crear(client, create_product)
    ids = [_body(_subir(client, product_id))["data"]["id"] for _ in range(3)]

    response = client.delete(
        f"{PRODUCTS_URL}/{product_id}/media/{ids[1]}", headers=PRODUCTOR
    )

    assert response.status_code == 200
    body = _body(response)
    assert body["message"] == "Medio eliminado correctamente."
    assert body["data"]["estado"] == "eliminado"
    assert body["data"]["totalMedios"] == 2
    assert [medio["id"] for medio in body["data"]["medios"]] == [ids[0], ids[2]]
    assert [medio["orden"] for medio in body["data"]["medios"]] == [1, 2]

    visibles = _body(client.get(f"{PRODUCTS_URL}/{product_id}"))["data"]["medios"]
    assert [medio["id"] for medio in visibles] == [ids[0], ids[2]]
    assert client.delete(
        f"{PRODUCTS_URL}/{product_id}/media/{ids[1]}", headers=PRODUCTOR
    ).status_code == 404


# Seguridad y estados --------------------------------------------------------
def test_archivo_rechazado_por_escaneo_no_se_asocia(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _crear(client, create_product)

    response = _subir(
        client, product_id, contenido=PNG + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"
    )

    assert response.status_code == 400
    assert _body(response)["data"]["codigo"] == "MEDIA_SCAN_REJECTED"
    assert _body(client.get(f"{PRODUCTS_URL}/{product_id}"))["data"]["medios"] == []


def test_medios_requieren_estado_editable(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _crear(
        client,
        create_product,
        medios=[{"tipo": "imagen", "url": "https://cdn.test/inicial.webp"}],
    )
    revision = client.post(f"{PRODUCTS_URL}/{product_id}/submit-review", headers=PRODUCTOR)
    assert revision.status_code == 200

    assert _subir(client, product_id).status_code == 409
    assert client.delete(
        f"{PRODUCTS_URL}/{product_id}/media/med_001", headers=PRODUCTOR
    ).status_code == 409


def test_sin_archivo_devuelve_400(
    client: TestClient, create_product: Callable[..., Any]
):
    product_id = _crear(client, create_product)

    response = client.post(f"{PRODUCTS_URL}/{product_id}/media", headers=PRODUCTOR)

    assert response.status_code == 400
    assert _body(response)["data"]["codigo"] == "MEDIA_FILE_REQUIRED"


def test_carga_y_eliminacion_se_auditan(
    client: TestClient, create_product: Callable[..., Any], product_service
):
    product_id = _crear(client, create_product)
    media_id = _body(_subir(client, product_id))["data"]["id"]
    client.delete(f"{PRODUCTS_URL}/{product_id}/media/{media_id}", headers=PRODUCTOR)

    eventos = product_service.audit_repository.list_for_entity(
        product_id, entidad="producto"
    )
    assert [evento["accion"] for evento in eventos] == [
        "crear",
        "cargar_medio",
        "eliminar_medio",
    ]
    assert {evento["actorId"] for evento in eventos} == {"usr_010"}
    assert eventos[-1]["cambios"]["totalMedios"] == 0


def test_cargar_medio_invalida_la_vitrina_de_hu10(
    client: TestClient, create_product: Callable[..., Any], showcase_cache
):
    categoria_id = _body(
        client.post(CATEGORIES_URL, json={"nombre": "Vitrina con medios"})
    )["data"]["id"]
    producto = create_product(
        headers=PRODUCTOR, categoria_id=categoria_id, medios=[]
    )
    product_id = _body(producto)["data"]["id"]
    assert client.patch(
        f"{PRODUCTS_URL}/{product_id}/archive", headers=PRODUCTOR
    ).status_code == 200
    assert client.patch(
        f"{PRODUCTS_URL}/{product_id}/reactivate", headers=PRODUCTOR
    ).status_code == 200

    assert client.get("/api/v1/catalog/showcase").status_code == 200
    assert showcase_cache.get(categoria_id) is not None

    respuesta = _subir(client, product_id)
    assert respuesta.status_code == 201
    url = _body(respuesta)["data"]["url"]
    assert showcase_cache.get(categoria_id) is None

    data = _body(client.get("/api/v1/catalog/showcase"))["data"]
    producto_vitrina = next(
        item
        for grupo in data["categorias"]
        for item in grupo["productos"]
        if item["id"] == product_id
    )
    assert producto_vitrina["miniatura"] == url
