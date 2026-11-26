"""Reglas puras de medios del producto (SUB-10, FUN-26/FUN-27).

La validación de formato se hace con la **firma binaria** del archivo, nunca con
la extensión o el ``Content-Type`` declarados por el cliente: esos dos solo se
usan como comprobación adicional de coherencia. Los formatos y los límites
numéricos viven en ``Settings`` (CAT-05 a CAT-10) y se pasan a estas funciones.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath

from app.domain.exceptions import (
    InvalidMediaFormatError,
    MediaLimitError,
    MediaTooLargeError,
)
from app.domain.product import MEDIO_ACTIVO, MEDIO_ELIMINADO, Medio

# Firmas de los formatos candidatos. ``offset`` permite reconocer MP4/MOV, cuya
# marca ``ftyp`` aparece en el byte 4.
@dataclass(frozen=True)
class _Firma:
    offset: int
    valor: bytes


@dataclass(frozen=True)
class FormatoMedio:
    clave: str
    tipo: str
    extensiones: frozenset[str]
    mime: str
    codigo: str
    firmas: tuple[_Firma, ...]

    def accepts(self, contenido: bytes) -> bool:
        # Todas las firmas declaradas deben coincidir: MOV exige ``ftyp`` y la
        # marca ``qt  ``; WEBP exige ``RIFF`` y ``WEBP``.
        return all(
            contenido[firma.offset : firma.offset + len(firma.valor)] == firma.valor
            for firma in self.firmas
        )


# CAT-05: imágenes. CAT-07: videos. GIF queda fuera deliberadamente.
FORMATOS_DISPONIBLES: dict[str, FormatoMedio] = {
    "jpg": FormatoMedio(
        clave="jpg",
        tipo="imagen",
        extensiones=frozenset({"jpg", "jpeg"}),
        mime="image/jpeg",
        codigo="CAT-05",
        firmas=(_Firma(0, b"\xff\xd8\xff"),),
    ),
    "png": FormatoMedio(
        clave="png",
        tipo="imagen",
        extensiones=frozenset({"png"}),
        mime="image/png",
        codigo="CAT-05",
        firmas=(_Firma(0, b"\x89PNG\r\n\x1a\n"),),
    ),
    "webp": FormatoMedio(
        clave="webp",
        tipo="imagen",
        extensiones=frozenset({"webp"}),
        mime="image/webp",
        codigo="CAT-05",
        firmas=(_Firma(0, b"RIFF"), _Firma(8, b"WEBP")),
    ),
    "mp4": FormatoMedio(
        clave="mp4",
        tipo="video",
        extensiones=frozenset({"mp4", "m4v"}),
        mime="video/mp4",
        codigo="CAT-07",
        firmas=(_Firma(4, b"ftyp"),),
    ),
    "mov": FormatoMedio(
        clave="mov",
        tipo="video",
        extensiones=frozenset({"mov"}),
        mime="video/quicktime",
        codigo="CAT-07",
        # Las firmas se evalúan en orden: MOV se reconoce antes que MP4.
        firmas=(_Firma(4, b"ftyp"), _Firma(8, b"qt  ")),
    ),
    "webm": FormatoMedio(
        clave="webm",
        tipo="video",
        extensiones=frozenset({"webm"}),
        mime="video/webm",
        codigo="CAT-07",
        firmas=(_Firma(0, b"\x1a\x45\xdf\xa3"),),
    ),
}

# Se comprueban primero las firmas más específicas (MOV antes que MP4).
_ORDEN_DETECCION = ("jpg", "png", "webp", "mov", "mp4", "webm")

_FORMATOS_RECHAZADOS: tuple[tuple[bytes, str], ...] = (
    (b"GIF87a", "GIF"),
    (b"GIF89a", "GIF"),
    (b"%PDF-", "PDF"),
    (b"PK\x03\x04", "ZIP"),
    (b"\x7fELF", "ELF"),
    (b"BM", "BMP"),
)


@dataclass(frozen=True)
class ArchivoMedio:
    """Archivo recibido por la API, aún sin validar ni almacenar."""

    nombre: str
    contenido: bytes
    content_type: str = ""
    tamano: int | None = None

    @property
    def extension(self) -> str:
        return PurePath(self.nombre).suffix.lower().lstrip(".")


@dataclass(frozen=True)
class FormatoDetectado:
    formato: FormatoMedio
    extension: str


def formatos_permitidos(
    imagenes: tuple[str, ...], videos: tuple[str, ...]
) -> tuple[FormatoMedio, ...]:
    """Materializa CAT-05 y CAT-07 a partir de la configuración."""

    claves = tuple(imagenes) + tuple(videos)
    return tuple(
        FORMATOS_DISPONIBLES[clave]
        for clave in _ORDEN_DETECCION
        if clave in claves and clave in FORMATOS_DISPONIBLES
    )


def detectar_formato(
    archivo: ArchivoMedio, *, formatos: tuple[FormatoMedio, ...]
) -> FormatoDetectado:
    """Detecta el tipo real del archivo y comprueba extensión y MIME."""

    permitidos = sorted(ext for formato in formatos for ext in formato.extensiones)
    if not archivo.contenido:
        raise InvalidMediaFormatError(
            "El archivo de medio está vacío.",
            details={"campo": "archivo", "permitidos": permitidos},
        )

    formato = next((item for item in formatos if item.accepts(archivo.contenido)), None)
    if formato is None:
        rechazado = next(
            (nombre for firma, nombre in _FORMATOS_RECHAZADOS if archivo.contenido.startswith(firma)),
            None,
        )
        raise InvalidMediaFormatError(
            "Formato de medio no permitido (CAT-05/CAT-07)."
            if rechazado is None
            else f"El formato {rechazado} no está permitido (CAT-05/CAT-07).",
            details={
                "campo": "archivo",
                "formato": rechazado,
                "permitidos": permitidos,
            },
        )

    if archivo.extension and archivo.extension not in formato.extensiones:
        raise InvalidMediaFormatError(
            "La extensión del archivo no coincide con su contenido (CAT-05/CAT-07).",
            details={
                "campo": "archivo",
                "extension": archivo.extension,
                "detectado": formato.clave,
                "permitidos": permitidos,
            },
        )

    mime = archivo.content_type.strip().lower().split(";", 1)[0]
    prefijo_mime = "image/" if formato.tipo == "imagen" else "video/"
    if mime and mime != "application/octet-stream" and not mime.startswith(prefijo_mime):
        raise InvalidMediaFormatError(
            "El tipo declarado no coincide con el contenido del archivo (CAT-05/CAT-07).",
            details={
                "campo": "archivo",
                "contentType": archivo.content_type,
                "detectado": formato.tipo,
            },
        )

    extension = archivo.extension or sorted(formato.extensiones)[0]
    return FormatoDetectado(formato=formato, extension=extension)


def validate_tamano(
    archivo: ArchivoMedio, *, maximo: int, codigo: str
) -> int:
    """CAT-06/CAT-08. Devuelve el tamaño validado en bytes."""

    tamano = max(len(archivo.contenido), int(archivo.tamano or 0))
    if tamano > maximo:
        raise MediaTooLargeError(
            f"El archivo supera el tamaño máximo permitido ({codigo}).",
            details={
                "campo": "archivo",
                "codigo": codigo,
                "tamanoBytes": tamano,
                "maximoBytes": maximo,
            },
        )
    return tamano


def ensure_cantidad(actuales: int, *, maximo: int) -> None:
    """CAT-10: número máximo de medios activos por producto."""

    if actuales >= maximo:
        raise MediaLimitError(
            f"El producto ya alcanzó el máximo de {maximo} medios (CAT-10).",
            details={"campo": "medios", "codigo": "CAT-10", "actuales": actuales, "maximo": maximo},
        )


def medios_activos(medios: list[Medio]) -> list[Medio]:
    return [medio for medio in medios if medio.estado != MEDIO_ELIMINADO]


def siguiente_orden(medios: list[Medio]) -> int:
    return len(medios_activos(medios)) + 1


def reordenar_medios(medios: list[Medio]) -> list[Medio]:
    """Numera los medios visibles de 1 a N tras un borrado lógico."""

    orden = 0
    resultado: list[Medio] = []
    for medio in medios:
        if medio.estado == MEDIO_ELIMINADO:
            resultado.append(medio)
            continue
        orden += 1
        resultado.append(
            Medio(
                id=medio.id,
                tipo=medio.tipo,
                url=medio.url,
                orden=orden,
                estado=medio.estado,
            )
        )
    return resultado


def marcar_eliminado(medio: Medio) -> Medio:
    return Medio(
        id=medio.id,
        tipo=medio.tipo,
        url=medio.url,
        orden=medio.orden,
        estado=MEDIO_ELIMINADO,
    )


def medio_activo(medio: Medio) -> bool:
    return medio.estado == MEDIO_ACTIVO
