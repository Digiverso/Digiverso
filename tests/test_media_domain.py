"""Pruebas unitarias de las reglas puras de medios (HU-09)."""

from __future__ import annotations

import base64

import pytest

from app.domain.exceptions import (
    InvalidMediaFormatError,
    MediaLimitError,
    MediaTooLargeError,
)
from app.domain.media import (
    ArchivoMedio,
    detectar_formato,
    ensure_cantidad,
    formatos_permitidos,
    marcar_eliminado,
    medios_activos,
    reordenar_medios,
    siguiente_orden,
    validate_tamano,
)
from app.domain.product import MEDIO_ELIMINADO, Medio
from app.services.media_scan import SignatureFileScanner

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/"
    "q842iQAAAABJRU5ErkJggg=="
)
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 16 + b"\xff\xd9"
GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 16
WEBM = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\xf7\x81\x01\x42\x82\x84webm"

FORMATOS = formatos_permitidos(("jpg", "png", "webp"), ("mp4", "mov", "webm"))


def _archivo(nombre: str, contenido: bytes, mime: str) -> ArchivoMedio:
    return ArchivoMedio(nombre=nombre, contenido=contenido, content_type=mime)


def test_firma_binaria_por_formato_cat_05_y_cat_07():
    casos = (
        ("foto.png", PNG, "image/png", "png", "imagen"),
        ("foto.jpeg", JPEG, "image/jpeg", "jpg", "imagen"),
        ("video.mp4", MP4, "video/mp4", "mp4", "video"),
        ("video.webm", WEBM, "video/webm", "webm", "video"),
    )
    for nombre, contenido, mime, clave, tipo in casos:
        detectado = detectar_formato(_archivo(nombre, contenido, mime), formatos=FORMATOS)
        assert detectado.formato.clave == clave
        assert detectado.formato.tipo == tipo


def test_gif_no_esta_permitido_cat_05():
    with pytest.raises(InvalidMediaFormatError) as error:
        detectar_formato(_archivo("anim.gif", GIF, "image/gif"), formatos=FORMATOS)
    assert error.value.status_code == 400
    assert "GIF" in error.value.message


def test_extension_o_mime_incoherentes_se_rechazan():
    with pytest.raises(InvalidMediaFormatError):
        detectar_formato(_archivo("foto.mp4", PNG, "image/png"), formatos=FORMATOS)
    with pytest.raises(InvalidMediaFormatError):
        detectar_formato(_archivo("foto.png", PNG, "video/mp4"), formatos=FORMATOS)


def test_tamano_maximo_cat_06_devuelve_413():
    with pytest.raises(MediaTooLargeError) as error:
        validate_tamano(_archivo("foto.png", PNG, "image/png"), maximo=10, codigo="CAT-06")
    assert error.value.status_code == 413
    assert error.value.details["codigo"] == "CAT-06"


def test_cantidad_maxima_cat_10_devuelve_409():
    ensure_cantidad(9, maximo=10)
    with pytest.raises(MediaLimitError) as error:
        ensure_cantidad(10, maximo=10)
    assert error.value.status_code == 409
    assert error.value.details["codigo"] == "CAT-10"


def test_borrado_logico_reordena_los_restantes():
    medios = [
        Medio(id="med_001", url="u1", orden=1),
        Medio(id="med_002", url="u2", orden=2),
        Medio(id="med_003", url="u3", orden=3),
    ]
    assert siguiente_orden(medios) == 4

    restantes = reordenar_medios(
        [marcar_eliminado(medio) if medio.id == "med_002" else medio for medio in medios]
    )
    activos = medios_activos(restantes)
    assert [medio.id for medio in activos] == ["med_001", "med_003"]
    assert [medio.orden for medio in activos] == [1, 2]
    assert [medio.estado for medio in restantes if medio.id == "med_002"] == [MEDIO_ELIMINADO]


def test_scanner_rechaza_eicar_y_ejecutables():
    scanner = SignatureFileScanner()
    assert scanner.scan(PNG).seguro is True
    assert scanner.scan(PNG + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE").seguro is False
    assert scanner.scan(b"MZ" + b"\x00" * 32 + b"PE\x00\x00").seguro is False
