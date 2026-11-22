"""Entidad y reglas puras del árbol de categorías (SUB-08)."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.domain.exceptions import InvalidCategoryError

ESTADO_ACTIVA = "activa"
ESTADO_INACTIVA = "inactiva"
ROOT_PATH = "/"


def normalize_name(value: str) -> str:
    """Normaliza un nombre para compararlo sin mayúsculas ni tildes.

    ``Ilustración  Digital`` y ``ilustracion digital`` producen la misma clave.
    """

    decomposed = unicodedata.normalize("NFKD", value.strip())
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(without_marks.casefold().split())


def validate_name(value: str, *, min_length: int, max_length: int) -> str:
    """Valida la longitud CAT-17 y devuelve el nombre recortado."""

    nombre = value.strip() if isinstance(value, str) else ""
    longitud = len(nombre)
    if longitud < min_length or longitud > max_length:
        raise InvalidCategoryError(
            f"El nombre de la categoría debe tener entre {min_length} y {max_length} caracteres (CAT-17).",
            details={"longitud": longitud, "minimo": min_length, "maximo": max_length},
        )
    return nombre


def validate_order(orden: int) -> int:
    if orden < 0:
        raise InvalidCategoryError(
            "El orden de la categoría no puede ser negativo.",
            details={"orden": orden},
        )
    return orden


def build_path(parent: Category | None, category_id: str) -> str:
    """Construye la ruta materializada incluyendo la propia categoría."""

    if parent is None:
        return f"{ROOT_PATH}{category_id}/"
    return f"{parent.ruta}{category_id}/"


def is_self_or_descendant(candidate: Category, ancestor: Category) -> bool:
    """Indica si ``candidate`` es ``ancestor`` o está debajo de él."""

    return candidate.id == ancestor.id or candidate.ruta.startswith(ancestor.ruta)


@dataclass
class Category:
    id: str
    nombre: str
    padre_id: str | None = None
    estado: str = ESTADO_ACTIVA
    orden: int = 0
    descripcion: str | None = None
    ruta: str = ROOT_PATH
    creado_en: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    actualizado_en: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    eliminado_en: datetime | None = None

    @property
    def nombre_normalizado(self) -> str:
        return normalize_name(self.nombre)

    @property
    def activa(self) -> bool:
        return self.estado == ESTADO_ACTIVA
