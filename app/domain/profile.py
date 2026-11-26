from __future__ import annotations

import base64
import binascii
from pathlib import Path
from urllib.parse import urlsplit

from app.domain.auth import DomainError

FORMATOS: dict[str, tuple[bytes, str, str]] = {
    "jpeg": (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    "png": (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    "webp": (b"WEBP", "webp", "image/webp"),
}


class InvalidProfileError(DomainError):
    status_code = 400
    codigo = "perfil_invalido"

    def __init__(
        self,
        message: str,
        *,
        campo: str,
        detalles: dict[str, object] | None = None,
    ) -> None:
        data: dict[str, object] = {"codigo": self.codigo, "campo": campo}
        if detalles is not None:
            data["detalle"] = detalles
        super().__init__(message, data)


def normalizar_formato(valor: str) -> str:
    return "jpeg" if valor.strip().lower() in {"jpg", "jpeg"} else valor.strip().lower()


def detectar_formato(
    contenido: bytes,
    permitidos: tuple[str, ...],
) -> tuple[str, str, str]:
    formatos_permitidos = {normalizar_formato(formato) for formato in permitidos}
    for formato, (firma, extension, mime) in FORMATOS.items():
        if formato not in formatos_permitidos:
            continue
        if formato == "webp":
            es_webp = len(contenido) >= 12 and contenido[:4] == b"RIFF" and contenido[8:12] == firma
            if es_webp:
                return formato, extension, mime
            continue
        if contenido.startswith(firma):
            return formato, extension, mime
    raise InvalidProfileError(
        "La imagen no corresponde a un formato permitido.",
        campo="foto",
        detalles={"formatosPermitidos": sorted(formatos_permitidos)},
    )


def validar_tamano(contenido: bytes, maximo: int) -> None:
    if len(contenido) > maximo:
        raise InvalidProfileError(
            "La foto excede el tamaño máximo permitido.",
            campo="foto",
            detalles={"tamano": len(contenido), "maximo": maximo},
        )


def decodificar_data_url(valor: str) -> bytes:
    cabecera, separador, codificado = valor.partition(",")
    if (
        not separador
        or not cabecera.lower().startswith("data:image/")
        or ";base64" not in cabecera.lower()
    ):
        raise InvalidProfileError(
            "La foto debe ser una URL de imagen válida o un data URL base64.",
            campo="foto",
        )
    try:
        return base64.b64decode(codificado.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError) as exc:
        raise InvalidProfileError(
            "La imagen base64 no es válida.",
            campo="foto",
        ) from exc


def validar_url_foto(valor: str, permitidos: tuple[str, ...]) -> str:
    parsed = urlsplit(valor)
    extension = normalizar_formato(Path(parsed.path).suffix.lstrip("."))
    formatos_permitidos = {normalizar_formato(formato) for formato in permitidos}
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise InvalidProfileError(
            "La URL de la foto no es válida.",
            campo="foto",
        )
    if extension not in formatos_permitidos:
        raise InvalidProfileError(
            "La extensión de la foto no corresponde a un formato permitido.",
            campo="foto",
            detalles={"extension": extension, "formatosPermitidos": sorted(formatos_permitidos)},
        )
    return valor


def mime_por_formato(formato: str) -> str:
    return FORMATOS.get(normalizar_formato(formato), ("", "", "application/octet-stream"))[2]
