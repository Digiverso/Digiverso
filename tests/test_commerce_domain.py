"""Pruebas puras de firma, vencimiento y paginación de HU-15."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.commerce import (
    build_signed_token,
    normalize_filename,
    object_key_for,
    validate_pagination,
    verify_signed_token,
)
from app.domain.exceptions import (
    ExpiredSignedUrlError,
    InvalidPaginationError,
    InvalidSignedUrlError,
)

SECRETO = "clave-de-prueba"
AHORA = datetime(2026, 10, 25, 18, 5, tzinfo=timezone.utc)


def _token(expira_en: datetime) -> str:
    return build_signed_token(
        object_key="prod_100/pack.webp",
        license_id="lic_900",
        purchase_id="ord_500",
        expires_at=expira_en,
        secret=SECRETO,
    )


def test_token_firmado_devuelve_carga_y_vence_en_el_plazo():
    token = _token(AHORA + timedelta(minutes=10))
    carga = verify_signed_token(token, secret=SECRETO, now=AHORA)

    assert carga.object_key == "prod_100/pack.webp"
    assert carga.licencia_id == "lic_900"
    assert carga.compra_id == "ord_500"
    assert carga.expira_en == AHORA + timedelta(minutes=10)


def test_token_modificado_o_con_otro_secreto_es_invalido():
    token = _token(AHORA + timedelta(minutes=10))
    cuerpo, firma = token.split(".", 1)
    alterado = f"{cuerpo}.{firma[:-1]}{'a' if firma[-1] != 'a' else 'b'}"

    with pytest.raises(InvalidSignedUrlError):
        verify_signed_token(alterado, secret=SECRETO, now=AHORA)
    with pytest.raises(InvalidSignedUrlError):
        verify_signed_token(token, secret="otro-secreto", now=AHORA)
    with pytest.raises(InvalidSignedUrlError):
        verify_signed_token("sin-firma", secret=SECRETO, now=AHORA)


def test_token_expirado_devuelve_410():
    token = _token(AHORA + timedelta(minutes=10))

    with pytest.raises(ExpiredSignedUrlError) as exc:
        verify_signed_token(
            token, secret=SECRETO, now=AHORA + timedelta(minutes=11)
        )
    assert exc.value.status_code == 410
    assert exc.value.code == "URL_EXPIRED"


def test_nombre_archivo_se_normaliza_y_conserva_extension():
    assert normalize_filename("¡Pack de Ilustraciones!", "https://cdn.test/uno.webp") == (
        "pack-de-ilustraciones.webp"
    )
    assert normalize_filename(",,,", "") == "producto"
    assert object_key_for("prod_100", "https://cdn.test/../uno.webp") == (
        "prod_100/uno.webp"
    )


def test_paginacion_acepta_valores_por_defecto_y_rechaza_fuera_de_rango():
    paginacion = validate_pagination(None, None, default_size=20, max_size=100)
    assert (paginacion.pagina, paginacion.tamanio_pagina, paginacion.offset) == (1, 20, 0)

    segunda = validate_pagination("2", "5", default_size=20, max_size=100)
    assert segunda.offset == 5

    with pytest.raises(InvalidPaginationError):
        validate_pagination(0, 20, default_size=20, max_size=100)
    with pytest.raises(InvalidPaginationError):
        validate_pagination(1, 101, default_size=20, max_size=100)
    with pytest.raises(InvalidPaginationError):
        validate_pagination("x", 20, default_size=20, max_size=100)
