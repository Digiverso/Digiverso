"""Entidad y reglas puras del ciclo de vida de productos (SUB-09).

Las reglas de contenido (CAT-01, CAT-03, CAT-09, CAT-11, CAT-12 y CAT-13) se
validan aquí, en el dominio, y no en los esquemas HTTP ni en el servicio.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from app.domain.exceptions import (
    InsufficientProductMediaError,
    InvalidProductError,
    InvalidProductStateError,
)

MONEDA_POR_DEFECTO = "COP"

ESTADO_BORRADOR = "borrador"
ESTADO_EN_REVISION = "en_revision"
ESTADO_PUBLICADO = "publicado"
ESTADO_RECHAZADO = "rechazado"
ESTADO_ARCHIVADO = "archivado"

ESTADOS = (
    ESTADO_BORRADOR,
    ESTADO_EN_REVISION,
    ESTADO_PUBLICADO,
    ESTADO_RECHAZADO,
    ESTADO_ARCHIVADO,
)

# FUN-22: el producto se puede editar en borrador, rechazado y publicado.
# También se admite ``archivado`` para poder preparar los cambios que, al
# reactivar, fuerzan una nueva revisión (FUN-25 / caso 6).
ESTADOS_EDITABLES = frozenset(
    {ESTADO_BORRADOR, ESTADO_RECHAZADO, ESTADO_PUBLICADO, ESTADO_ARCHIVADO}
)
ESTADOS_ENVIABLES_A_REVISION = frozenset(
    {ESTADO_BORRADOR, ESTADO_RECHAZADO, ESTADO_PUBLICADO}
)
ESTADOS_ARCHIVABLES = frozenset(
    {ESTADO_BORRADOR, ESTADO_EN_REVISION, ESTADO_PUBLICADO, ESTADO_RECHAZADO}
)

TIPOS_MEDIO = ("imagen", "video", "documento")
_ALIAS_TIPOS_MEDIO = {"image": "imagen", "images": "imagen", "video": "video", "document": "documento"}

# FUN-26/FUN-27: ciclo de estado de un medio. ``en_analisis`` y ``rechazado``
# son estados de tránsito del escaneo; solo ``activo`` y ``eliminado`` se
# persisten. Los medios eliminados siguen en la lista (borrado lógico) pero no
# cuentan para CAT-10 ni aparecen en la ficha del producto.
MEDIO_EN_ANALISIS = "en_analisis"
MEDIO_ACTIVO = "activo"
MEDIO_RECHAZADO = "rechazado"
MEDIO_ELIMINADO = "eliminado"
ESTADOS_MEDIO = (
    MEDIO_EN_ANALISIS,
    MEDIO_ACTIVO,
    MEDIO_RECHAZADO,
    MEDIO_ELIMINADO,
)
MEDIOS_VISIBLES = frozenset({MEDIO_EN_ANALISIS, MEDIO_ACTIVO})


def _es_entero(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class Medio:
    url: str
    tipo: str = "imagen"
    id: str | None = None
    orden: int = 0
    estado: str = MEDIO_ACTIVO

    @property
    def es_imagen(self) -> bool:
        return self.tipo == "imagen"

    @property
    def visible(self) -> bool:
        return self.estado in MEDIOS_VISIBLES


def build_medio(value: object) -> Medio:
    """Acepta una URL suelta o un objeto ``{tipo, url, id, orden}``.

    Normalizar aquí evita que la API tenga que decidir qué cuenta como imagen
    a la hora de aplicar CAT-09.
    """

    if isinstance(value, Medio):
        return value
    if isinstance(value, str):
        value = {"url": value}
    if not isinstance(value, Mapping):
        raise InvalidProductError(
            "Cada medio debe ser una URL o un objeto con ``url``.",
            details={"medio": str(value)},
        )

    raw_tipo = str(value.get("tipo", "imagen") or "imagen").strip().lower()
    tipo = _ALIAS_TIPOS_MEDIO.get(raw_tipo, raw_tipo)
    if tipo not in TIPOS_MEDIO:
        raise InvalidProductError(
            "El tipo de medio no es válido.",
            details={"tipo": raw_tipo, "permitidos": list(TIPOS_MEDIO)},
        )

    url = str(value.get("url") or "").strip()
    if not url:
        raise InvalidProductError("La URL del medio es obligatoria.", details={"campo": "medios.url"})

    orden = value.get("orden", 0)
    if orden is None:
        orden = 0
    if not _es_entero(orden) or orden < 0:
        raise InvalidProductError(
            "El orden del medio debe ser un entero no negativo.",
            details={"orden": orden},
        )

    estado = str(value.get("estado", MEDIO_ACTIVO) or MEDIO_ACTIVO).strip().lower()
    if estado not in ESTADOS_MEDIO:
        raise InvalidProductError(
            "El estado del medio no es válido.",
            details={"estado": estado, "permitidos": list(ESTADOS_MEDIO)},
        )

    return Medio(
        id=str(value["id"]) if value.get("id") else None,
        tipo=tipo,
        url=url,
        orden=int(orden),
        estado=estado,
    )


def validate_nombre(value: object, *, minimo: int, maximo: int) -> str:
    """Longitud CAT-11."""

    nombre = value.strip() if isinstance(value, str) else ""
    longitud = len(nombre)
    if longitud < minimo or longitud > maximo:
        raise InvalidProductError(
            f"El nombre del producto debe tener entre {minimo} y {maximo} caracteres (CAT-11).",
            details={"campo": "nombre", "longitud": longitud, "minimo": minimo, "maximo": maximo},
        )
    return nombre


def validate_descripcion(value: object, *, minimo: int, maximo: int) -> str:
    """Longitud CAT-12."""

    descripcion = value.strip() if isinstance(value, str) else ""
    longitud = len(descripcion)
    if longitud < minimo or longitud > maximo:
        raise InvalidProductError(
            f"La descripción debe tener entre {minimo} y {maximo} caracteres (CAT-12).",
            details={
                "campo": "descripcion",
                "longitud": longitud,
                "minimo": minimo,
                "maximo": maximo,
            },
        )
    return descripcion


def validate_precio(value: object, *, minimo: int, moneda: str) -> int:
    """Precio mínimo CAT-01 (expresado en COP)."""

    if str(moneda).strip().upper() != MONEDA_POR_DEFECTO:
        raise InvalidProductError(
            "La moneda del producto debe ser COP.",
            details={"campo": "moneda", "valor": moneda, "permitida": MONEDA_POR_DEFECTO},
        )
    if not _es_entero(value) or int(value) < 0:
        raise InvalidProductError(
            "El precio debe ser un entero no negativo.",
            details={"campo": "precio", "valor": value},
        )
    precio = int(value)
    if precio < minimo:
        raise InvalidProductError(
            f"El precio mínimo CAT-01 es {minimo} {MONEDA_POR_DEFECTO}.",
            details={"campo": "precio", "valor": precio, "minimo": minimo, "moneda": moneda},
        )
    return precio


def validate_edades(
    minima: object, maxima: object, *, maximo: int
) -> tuple[int, int]:
    """Rango de edad CAT-03."""

    if not _es_entero(minima) or not _es_entero(maxima):
        raise InvalidProductError(
            "Las edades deben ser enteros.",
            details={"edadMinima": minima, "edadMaxima": maxima},
        )
    edad_minima, edad_maxima = int(minima), int(maxima)
    if edad_minima < 0 or edad_maxima > maximo or edad_minima > edad_maxima:
        raise InvalidProductError(
            f"El rango de edad CAT-03 debe cumplir 0 <= edadMinima <= edadMaxima <= {maximo}.",
            details={
                "edadMinima": edad_minima,
                "edadMaxima": edad_maxima,
                "maximo": maximo,
            },
        )
    return edad_minima, edad_maxima


def validate_categorias(value: object, *, maximo: int) -> list[str]:
    """Categorías CAT-13: al menos una, únicas y sin espacios sobrantes."""

    if not isinstance(value, (list, tuple)):
        raise InvalidProductError(
            "El producto debe declarar al menos una categoría (CAT-13).",
            details={"campo": "categorias"},
        )
    categorias = [str(item).strip() for item in value]
    if not categorias or len(categorias) > maximo:
        raise InvalidProductError(
            f"El producto admite entre 1 y {maximo} categorías (CAT-13).",
            details={"cantidad": len(categorias), "maximo": maximo},
        )
    if any(not categoria for categoria in categorias):
        raise InvalidProductError(
            "Los identificadores de categoría no pueden estar vacíos (CAT-13).",
            details={"campo": "categorias"},
        )
    if len(set(categorias)) != len(categorias):
        raise InvalidProductError(
            "Las categorías no pueden repetirse (CAT-13).",
            details={"categorias": categorias},
        )
    return categorias


def validate_calificacion(value: object) -> float:
    """Calificación pública (0–5); ``0`` cuando aún no hay reseñas."""

    if value is None:
        return 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidProductError(
            "La calificación debe ser un número entre 0 y 5.",
            details={"campo": "calificacion", "valor": value},
        )
    calificacion = round(float(value), 1)
    if calificacion < 0 or calificacion > 5:
        raise InvalidProductError(
            "La calificación debe estar entre 0 y 5.",
            details={"campo": "calificacion", "valor": calificacion},
        )
    return calificacion


def validate_medios(value: object) -> list[Medio]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise InvalidProductError(
            "``medios`` debe ser una lista.", details={"campo": "medios"}
        )
    return [build_medio(item) for item in value]


def ensure_min_images(medios: list[Medio], *, minimo: int) -> None:
    """Cantidad mínima de imágenes CAT-09 para enviar a revisión."""

    imagenes = sum(1 for medio in medios if medio.es_imagen)
    if imagenes < minimo:
        raise InsufficientProductMediaError(
            f"Se requieren al menos {minimo} imagen(es) para enviar el producto a revisión (CAT-09).",
            details={
                "requeridas": minimo,
                "actuales": imagenes,
                "codigo": "CAT-09",
            },
        )


def ensure_transition(estado: str, permitidos: frozenset[str], accion: str) -> None:
    if estado not in permitidos:
        raise InvalidProductStateError(
            f"No se puede {accion} un producto en estado ``{estado}``.",
            details={
                "estado": estado,
                "accion": accion,
                "estadosPermitidos": sorted(permitidos),
            },
        )


@dataclass
class Product:
    id: str
    nombre: str
    descripcion: str
    precio: int
    autor_id: str
    categoria_id: str | None = None
    autor_nombre: str = ""
    calificacion: float = 0.0
    moneda: str = MONEDA_POR_DEFECTO
    edad_minima: int = 0
    edad_maxima: int = 99
    categorias: list[str] = field(default_factory=list)
    medios: list[Medio] = field(default_factory=list)
    estado: str = ESTADO_BORRADOR
    activo: bool = False
    creado_en: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    actualizado_en: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    estado_desde: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    archivado_en: datetime | None = None
    archivo_hash: str | None = None
    cambios_pendientes: bool = False

    @property
    def publicado(self) -> bool:
        return self.estado == ESTADO_PUBLICADO and self.activo

    @property
    def miniatura(self) -> str | None:
        """Primera imagen declarada; se usa en la vitrina y en la búsqueda."""

        for medio in sorted(self.medios, key=lambda item: item.orden):
            if medio.es_imagen:
                return medio.url
        return None

    def content(self) -> dict[str, Any]:
        """Contenido comparado al reactivar después de un archivo."""

        return {
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "precio": self.precio,
            "moneda": self.moneda,
            "edadMinima": self.edad_minima,
            "edadMaxima": self.edad_maxima,
            "categorias": list(self.categorias),
            "medios": [
                {"id": medio.id, "tipo": medio.tipo, "url": medio.url, "orden": medio.orden}
                for medio in self.medios
                if medio.visible
            ],
        }

    def content_hash(self) -> str:
        payload = json.dumps(self.content(), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
