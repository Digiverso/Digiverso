"""Pruebas de aceptación de HU-06 sobre la API HTTP."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import (
    AUTH_PARAMETERS_URL,
    PASSWORD,
    extraer_token,
    payload_registro,
)

ADMIN_HEADERS: dict[str, str] = {}
PRODUCER_HEADERS = {"X-Actor-Id": "usr_productor", "X-Actor-Roles": "productor"}
CATALOG_SCOPE_HEADERS = {
    "X-Actor-Id": "usr_catalogo",
    "X-Actor-Roles": "catalog.category.write",
}
SECURITY_SCOPE_HEADERS = {
    "X-Actor-Id": "usr_seguridad",
    "X-Actor-Roles": "admin.auth.parameters.write",
}


def _get(client: TestClient, suffix: str = "", headers: dict[str, str] | None = None):
    return client.get(f"{AUTH_PARAMETERS_URL}{suffix}", headers=headers or ADMIN_HEADERS)


def _put(client: TestClient, payload: dict[str, Any], headers: dict[str, str] | None = None):
    return client.put(AUTH_PARAMETERS_URL, json=payload, headers=headers or ADMIN_HEADERS)


# Caso 1 --------------------------------------------------------------------
def test_consulta_devuelve_version_vigencia_y_metadatos(client: TestClient) -> None:
    response = _get(client)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Parámetros de autenticación consultados correctamente."
    data = body["data"]
    assert data["version"] == 1
    assert data["vigenteDesde"].endswith(("Z", "+00:00"))
    assert data["parametros"] == {
        "AUT-01": 5,
        "AUT-02": 8,
        "AUT-03": 15,
        "AUT-04": 7,
        "AUT-05": 15,
        "AUT-06": 15,
        "AUT-07": 30,
    }
    por_codigo = {item["codigo"]: item for item in data["definiciones"]}
    assert set(por_codigo) == set(data["parametros"])
    assert por_codigo["AUT-01"]["valor"] == 5
    assert por_codigo["AUT-01"]["tipo"] == "entero"
    assert por_codigo["AUT-01"]["validacion"] == {
        "tipo": "entero",
        "minimo": 3,
        "maximo": 10,
        "requerido": True,
    }


# Caso 2 --------------------------------------------------------------------
def test_actualizacion_valida_crea_version_y_auditoria(
    client: TestClient, auth_parameters_service
) -> None:
    response = _put(
        client,
        {"parametros": {"AUT-01": 10}, "motivo": "Política reforzada"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Parámetros de autenticación actualizados."
    assert body["success"] is True
    data = body["data"]
    assert data["version"] == 2
    assert data["parametros"]["AUT-01"] == 10
    assert data["actualizadoPor"] == "usr_admin"
    assert data["motivo"] == "Política reforzada"

    eventos = auth_parameters_service.audit_repository.list_for_entity(
        "auth:version-2", entidad="parametros_autenticacion"
    )
    assert len(eventos) == 1
    assert eventos[0]["accion"] == "parametros_actualizados"
    assert eventos[0]["actorId"] == "usr_admin"
    assert eventos[0]["cambios"]["anteriores"] == {"AUT-01": 5}
    assert eventos[0]["cambios"]["versionAnterior"] == 1


# Caso 3 --------------------------------------------------------------------
def test_valor_fuera_de_rango_responde_400_y_no_modifica(client: TestClient) -> None:
    respuesta = _put(client, {"parametros": {"AUT-01": 2}})

    assert respuesta.status_code == 400
    cuerpo = respuesta.json()
    assert cuerpo["success"] is False
    assert cuerpo["data"]["versionActual"] == 1
    assert cuerpo["data"]["errores"][0]["motivo"] == "fuera_de_rango"
    assert cuerpo["data"]["errores"][0]["codigo"] == "AUT-01"

    actual = _get(client).json()["data"]
    assert actual["version"] == 1
    assert actual["parametros"]["AUT-01"] == 5


def test_tipo_invalido_responde_400_y_no_modifica(client: TestClient) -> None:
    respuesta = _put(client, {"parametros": {"AUT-01": "diez"}})

    assert respuesta.status_code == 400
    assert respuesta.json()["data"]["errores"][0]["motivo"] == "tipo_invalido"
    assert _get(client).json()["data"]["version"] == 1


def test_dependencia_incumplida_responde_400(client: TestClient) -> None:
    respuesta = _put(client, {"parametros": {"AUT-05": 1440}})

    assert respuesta.status_code == 400
    errores = respuesta.json()["data"]["errores"]
    assert any(error["motivo"] == "dependencia" for error in errores)
    assert _get(client).json()["data"]["version"] == 1


def test_peticion_sin_parametros_responde_400(client: TestClient) -> None:
    respuesta = _put(client, {"parametros": {}})

    assert respuesta.status_code == 400
    assert respuesta.json()["data"]["motivo"] == "sin_parametros"


# Caso 4 --------------------------------------------------------------------
def test_productor_no_puede_consultar_ni_actualizar(client: TestClient) -> None:
    consulta = _get(client, headers=PRODUCER_HEADERS)
    escritura = _put(
        client, {"parametros": {"AUT-01": 10}}, headers=PRODUCER_HEADERS
    )

    assert consulta.status_code == 403
    assert escritura.status_code == 403
    assert escritura.json()["success"] is False
    assert _get(client).json()["data"]["version"] == 1


def test_alcance_de_otro_modulo_no_habilita_escritura(client: TestClient) -> None:
    respuesta = _put(
        client, {"parametros": {"AUT-01": 10}}, headers=CATALOG_SCOPE_HEADERS
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["data"]["actorId"] == "usr_catalogo"


def test_alcance_explicito_de_autenticacion_habilita_escritura(
    client: TestClient,
) -> None:
    respuesta = _put(
        client, {"parametros": {"AUT-01": 10}}, headers=SECURITY_SCOPE_HEADERS
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["data"]["actualizadoPor"] == "usr_seguridad"


# Caso 5 --------------------------------------------------------------------
def test_historial_muestra_versiones_anteriores(client: TestClient) -> None:
    assert _put(client, {"parametros": {"AUT-01": 10}}).status_code == 200
    assert _put(client, {"parametros": {"AUT-06": 5}}).status_code == 200

    respuesta = _get(client, "/history")
    assert respuesta.status_code == 200
    data = respuesta.json()["data"]
    assert data["versionActual"] == 3
    assert data["total"] == 3
    assert [item["version"] for item in data["versiones"]] == [3, 2, 1]
    assert data["versiones"][0]["anteriores"] == {"AUT-06": 15}
    assert data["versiones"][0]["actual"] is True
    assert data["versiones"][-1]["actorId"] == "sistema"
    assert data["versiones"][-1]["parametros"]["AUT-01"] == 5

    inicial = _get(client, "/history/1")
    assert inicial.status_code == 200
    assert inicial.json()["data"]["parametros"]["AUT-01"] == 5
    assert _get(client, "/history/999").status_code == 404


# Aislamiento de módulos -----------------------------------------------------
def test_no_se_puede_modificar_otro_modulo(client: TestClient) -> None:
    por_modulo = _put(
        client, {"modulo": "catalogo", "parametros": {"AUT-01": 10}}
    )
    por_codigo = _put(client, {"parametros": {"CAT-01": 1000}})

    assert por_modulo.status_code == 400
    assert por_modulo.json()["data"]["moduloPermitido"] == "autenticacion"
    assert por_codigo.status_code == 400
    assert por_codigo.json()["data"]["modulo"] == "catalogo"
    assert _get(client).json()["data"]["version"] == 1


def test_codigo_desconocido_responde_400(client: TestClient) -> None:
    respuesta = _put(client, {"parametros": {"AUT-99": 1}})

    assert respuesta.status_code == 400
    assert respuesta.json()["data"]["codigo"] == "AUT-99"
    assert _get(client).json()["data"]["version"] == 1


# Caché y consumidores -------------------------------------------------------
class InvalidationSpy:
    def __init__(self, inner) -> None:
        self.inner = inner
        self.invalidations = 0
        self.hits = 0

    def get(self, version: int):
        snapshot = self.inner.get(version)
        if snapshot is not None:
            self.hits += 1
        return snapshot

    def set(self, snapshot) -> None:
        self.inner.set(snapshot)

    def invalidate(self) -> None:
        self.invalidations += 1
        self.inner.invalidate()


def test_cambio_invalida_cache_y_se_aplica_en_siguiente_peticion(
    client: TestClient, auth_parameters_service, service, email_gateway
) -> None:
    spy = InvalidationSpy(auth_parameters_service.cache)
    auth_parameters_service.cache = spy

    assert _get(client).json()["data"]["version"] == 1
    assert _get(client).json()["data"]["version"] == 1
    assert spy.hits == 1  # la segunda lectura provino de la caché

    respuesta = _put(client, {"parametros": {"AUT-01": 10}})
    assert respuesta.status_code == 200
    assert spy.invalidations == 1
    assert auth_parameters_service.value("AUT-01") == 10

    # El consumidor real (AuthService) lee el nuevo valor sin reiniciar.
    service.parameters = auth_parameters_service
    registro = client.post("/api/v1/auth/register", json=payload_registro())
    assert registro.status_code == 201
    verificado = client.post(
        "/api/v1/auth/email/verify", json={"token": extraer_token(email_gateway)}
    )
    assert verificado.status_code == 200

    intentos = [
        client.post(
            "/api/v1/auth/login",
            json={"correo": "ana@example.com", "password": "Incorrecta1!"},
        )
        for _ in range(6)
    ]
    # Con AUT-01=10 no se bloquea tras 6 fallos (el valor estático era 5).
    assert all(intento.status_code == 401 for intento in intentos)
    assert PASSWORD not in str([intento.json() for intento in intentos])
