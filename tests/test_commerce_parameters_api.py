"""Pruebas de aceptación de HU-17 sobre la API HTTP y sus consumidores."""

from __future__ import annotations

from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.actor import Actor
from app.main import create_app
from app.services.commerce_parameters import CommerceParametersService

COMMERCE_PARAMETERS_URL = "/api/v1/admin/commerce/parameters"
CATALOG_PARAMETERS_URL = "/api/v1/admin/catalog/parameters"

PRODUCER_HEADERS = {"X-Actor-Id": "usr_productor", "X-Actor-Roles": "productor"}
SCOPE_HEADERS = {
    "X-Actor-Id": "usr_parametros",
    "X-Actor-Roles": "admin.commerce.parameters.write",
}


@pytest.fixture()
def commerce_client(category_settings: Settings) -> Iterator[TestClient]:
    """Cliente sin sobrescribir servicios: ejercita la integración real."""

    application = create_app(category_settings)
    with TestClient(application) as client:
        yield client


def _service(client: TestClient) -> CommerceParametersService:
    return client.app.state.commerce_parameters_service


def _get(client: TestClient, suffix: str = "", headers: dict[str, str] | None = None):
    return client.get(f"{COMMERCE_PARAMETERS_URL}{suffix}", headers=headers or {})


def _put(
    client: TestClient, payload: dict[str, Any], headers: dict[str, str] | None = None
):
    return client.put(COMMERCE_PARAMETERS_URL, json=payload, headers=headers or {})


def client_settings(client: TestClient) -> Any:
    return client.app.state.settings


# Caso 1 --------------------------------------------------------------------
def test_consulta_devuelve_version_vigencia_y_metadatos(
    commerce_client: TestClient,
) -> None:
    response = _get(commerce_client)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Parámetros de comercio consultados correctamente."
    data = body["data"]
    assert data["version"] == 1
    assert data["vigenteDesde"].endswith(("Z", "+00:00"))
    assert data["modulo"] == "comercio"
    assert data["parametros"]["COM-01"] == 15
    assert data["parametros"]["COM-02"] == 85
    assert data["parametros"]["COM-10"] == 15
    por_codigo = {item["codigo"]: item for item in data["definiciones"]}
    assert set(por_codigo) == set(data["parametros"])
    assert por_codigo["COM-01"]["valor"] == 15
    assert por_codigo["COM-01"]["tipo"] == "entero"
    assert por_codigo["COM-01"]["validacion"]["maximo"] == 100
    assert por_codigo["COM-10"]["validacion"]["minimo"] == 1
    assert por_codigo["COM-03"]["tipo"] == "texto"
    assert "100 %" in por_codigo["COM-01"]["dependencias"][0]


# Caso 2 --------------------------------------------------------------------
def test_actualizacion_valida_crea_version_y_auditoria(
    commerce_client: TestClient,
) -> None:
    response = _put(
        commerce_client,
        {"parametros": {"COM-10": 10}, "motivo": "Nueva política de liquidación"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Parámetros de comercio actualizados."
    assert body["success"] is True
    data = body["data"]
    assert data["version"] == 2
    assert data["parametros"]["COM-10"] == 10
    assert data["actualizadoPor"] == "usr_admin"
    assert data["motivo"] == "Nueva política de liquidación"

    service = _service(commerce_client)
    eventos = service.audit_repository.list_for_entity(
        "commerce:version-2", entidad="parametros_comercio"
    )
    assert len(eventos) == 1
    assert eventos[0]["accion"] == "parametros_actualizados"
    assert eventos[0]["actorId"] == "usr_admin"
    assert eventos[0]["cambios"]["anteriores"] == {"COM-10": 15}
    assert eventos[0]["cambios"]["valores"] == {"COM-10": 10}
    assert eventos[0]["cambios"]["versionAnterior"] == 1
    assert service.cache.get(1) is None
    assert service.settings_view.commerce_payout_days == 10
    assert client_settings(commerce_client).commerce_payout_days == 10


def test_actualizacion_de_comision_y_neto_es_valida(
    commerce_client: TestClient,
) -> None:
    response = _put(
        commerce_client, {"parametros": {"COM-01": 20, "COM-02": 80}}
    )

    assert response.status_code == 200
    parametros = response.json()["data"]["parametros"]
    assert parametros["COM-01"] == 20
    assert parametros["COM-02"] == 80
    assert _service(commerce_client).settings_view.commerce_commission_percentage == 20


# Caso 3 --------------------------------------------------------------------
def test_porcentajes_inconsistentes_responde_400_y_no_modifica(
    commerce_client: TestClient,
) -> None:
    response = _put(commerce_client, {"parametros": {"COM-01": 10, "COM-02": 80}})

    assert response.status_code == 400
    assert response.json()["data"]["codigo"] == "COMMERCE_PARAMETER_INVALID"
    errores = response.json()["data"]["errores"]
    assert errores[0]["motivo"] == "porcentajes"
    assert errores[0]["suma"] == 90
    actual = _get(commerce_client).json()["data"]
    assert actual["version"] == 1
    assert actual["parametros"]["COM-01"] == 15
    assert actual["parametros"]["COM-02"] == 85


def test_no_se_puede_cambiar_solo_un_porcentaje(commerce_client: TestClient) -> None:
    response = _put(commerce_client, {"parametros": {"COM-01": 10}})

    assert response.status_code == 400
    assert _get(commerce_client).json()["data"]["parametros"]["COM-01"] == 15


def test_valor_fuera_de_rango_y_tipo_invalido_no_modifican(
    commerce_client: TestClient,
) -> None:
    fuera_de_rango = _put(commerce_client, {"parametros": {"COM-08": 0}})
    tipo_invalido = _put(commerce_client, {"parametros": {"COM-01": "20"}})

    assert fuera_de_rango.status_code == 400
    assert fuera_de_rango.json()["data"]["errores"][0]["motivo"] == "fuera_de_rango"
    assert tipo_invalido.status_code == 400
    assert tipo_invalido.json()["data"]["errores"][0]["motivo"] == "tipo_invalido"
    assert _get(commerce_client).json()["data"]["version"] == 1


def test_peticion_mal_formada_responde_400(commerce_client: TestClient) -> None:
    response = commerce_client.put(
        COMMERCE_PARAMETERS_URL, json={"parametros": "COM-10"}
    )

    assert response.status_code == 400
    assert response.json()["data"]["codigo"] == "validacion"


# Caso 4 --------------------------------------------------------------------
def test_acceso_indebido_devuelve_403(commerce_client: TestClient) -> None:
    assert _get(commerce_client, headers=PRODUCER_HEADERS).status_code == 403
    respuesta = _put(
        commerce_client, {"parametros": {"COM-10": 10}}, headers=PRODUCER_HEADERS
    )
    assert respuesta.status_code == 403
    assert respuesta.json()["data"]["codigo"] == "COMMERCE_PARAMETERS_FORBIDDEN"


def test_alcance_explicito_autoriza_actualizacion(
    commerce_client: TestClient,
) -> None:
    response = _put(
        commerce_client, {"parametros": {"COM-11": 60000}}, headers=SCOPE_HEADERS
    )

    assert response.status_code == 200
    assert response.json()["data"]["parametros"]["COM-11"] == 60000
    assert response.json()["data"]["actualizadoPor"] == "usr_parametros"


def test_alcance_de_otro_modulo_no_autoriza(commerce_client: TestClient) -> None:
    headers = {"X-Actor-Id": "usr_catalogo", "X-Actor-Roles": "catalog.category.write"}

    assert _get(commerce_client, headers=headers).status_code == 403
    assert _put(
        commerce_client, {"parametros": {"COM-10": 10}}, headers=headers
    ).status_code == 403


# Caso 5 --------------------------------------------------------------------
def test_historial_conserva_versiones_anteriores(commerce_client: TestClient) -> None:
    _put(commerce_client, {"parametros": {"COM-10": 10}})
    _put(commerce_client, {"parametros": {"COM-09": 5}})

    response = _get(commerce_client, "/history")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["versionActual"] == 3
    assert data["total"] == 3
    assert [item["version"] for item in data["versiones"]] == [3, 2, 1]
    assert data["versiones"][1]["anteriores"] == {"COM-10": 15}
    assert data["versiones"][2]["parametros"]["COM-09"] == 3
    assert data["versiones"][2]["actual"] is False
    assert data["versiones"][0]["actual"] is True
    assert (
        _get(commerce_client, "/history/1").json()["data"]["parametros"]["COM-10"]
        == 15
    )
    assert _get(commerce_client, "/history/999").status_code == 404


def test_historial_respeta_limite(commerce_client: TestClient) -> None:
    _put(commerce_client, {"parametros": {"COM-10": 10}})

    respuesta = _get(commerce_client, "/history?limit=1")

    assert respuesta.status_code == 200
    assert respuesta.json()["data"]["total"] == 1


# Aislamiento ---------------------------------------------------------------
def test_no_acepta_parametros_de_otros_modulos(commerce_client: TestClient) -> None:
    for codigo in ("AUT-01", "CAT-01", "COMU-01"):
        respuesta = _put(commerce_client, {"parametros": {codigo: 10}})
        assert respuesta.status_code == 400
        assert respuesta.json()["data"]["moduloPermitido"] == "comercio"
    assert _get(commerce_client).json()["data"]["version"] == 1


def test_no_acepta_modulo_ajeno(commerce_client: TestClient) -> None:
    respuesta = _put(
        commerce_client, {"modulo": "catalogo", "parametros": {"COM-10": 10}}
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["data"]["codigo"] == "COMMERCE_PARAMETER_MODULE"


def test_no_acepta_codigo_desconocido_ni_peticion_vacia(
    commerce_client: TestClient,
) -> None:
    desconocido = _put(commerce_client, {"parametros": {"COM-99": 1}})
    vacio = _put(commerce_client, {"parametros": {}})

    assert desconocido.status_code == 400
    assert desconocido.json()["data"]["modulo"] == "comercio"
    assert vacio.status_code == 400
    assert _get(commerce_client).json()["data"]["version"] == 1


def test_valores_de_otro_modulo_no_se_alteran(commerce_client: TestClient) -> None:
    _put(commerce_client, {"parametros": {"COM-10": 10}})

    catalogo = commerce_client.get(CATALOG_PARAMETERS_URL).json()["data"]

    assert catalogo["version"] == 1
    assert catalogo["parametros"]["CAT-01"] == 3500


# Consumidores --------------------------------------------------------------
def test_vista_de_settings_encadena_catalogo_y_comercio(
    commerce_client: TestClient,
) -> None:
    servicio = _service(commerce_client)
    actor = Actor(id="usr_admin", roles=("administrador",))

    assert servicio.settings_view.product_min_price == 3500
    assert servicio.settings_view.commerce_commission_percentage == 15

    catalogo = commerce_client.app.state.catalog_parameters_service
    catalogo.update(actor, parametros={"CAT-01": 4000})
    _put(commerce_client, {"parametros": {"COM-01": 18, "COM-02": 82}})

    settings = client_settings(commerce_client)
    assert settings.product_min_price == 4000
    assert settings.commerce_commission_percentage == 18
    assert settings.commerce_producer_percentage == 82
