"""Reglas puras de búsqueda, filtros, orden y paginación (HU-10).

Las decisiones de negocio viven aquí: normalización sin acentos, sinónimos,
tolerancia a errores tipográficos, validación CAT-01/CAT-03 y los órdenes
permitidos. El repositorio solo ejecuta la consulta y el servicio orquesta.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.domain.exceptions import InvalidCatalogQueryError

ORDEN_RELEVANCIA = "relevancia"
ORDEN_FECHA_DESC = "fecha_desc"
ORDEN_FECHA_ASC = "fecha_asc"
ORDEN_PRECIO_ASC = "precio_asc"
ORDEN_PRECIO_DESC = "precio_desc"

ORDENES_PERMITIDOS = (
    ORDEN_RELEVANCIA,
    ORDEN_FECHA_DESC,
    ORDEN_FECHA_ASC,
    ORDEN_PRECIO_ASC,
    ORDEN_PRECIO_DESC,
)

# Alias amables para la API; se normalizan antes de validar.
_ALIAS_ORDEN = {
    "relevancia": ORDEN_RELEVANCIA,
    "score": ORDEN_RELEVANCIA,
    "fecha": ORDEN_FECHA_DESC,
    "recientes": ORDEN_FECHA_DESC,
    "fecha_desc": ORDEN_FECHA_DESC,
    "fecha_asc": ORDEN_FECHA_ASC,
    "antiguos": ORDEN_FECHA_ASC,
    "precio": ORDEN_PRECIO_ASC,
    "precio_asc": ORDEN_PRECIO_ASC,
    "precio_desc": ORDEN_PRECIO_DESC,
    "menor_precio": ORDEN_PRECIO_ASC,
    "mayor_precio": ORDEN_PRECIO_DESC,
}

# Sinónimos del índice. Se guardan junto al producto para que la expansión no
# dependa de la consulta y la búsqueda por "dibujo" encuentre "ilustraciones".
SINONIMOS: dict[str, tuple[str, ...]] = {
    "ilustracion": ("ilustraciones", "dibujo", "dibujos", "arte", "imagen"),
    "dibujo": ("ilustracion", "ilustraciones", "arte"),
    "imagen": ("foto", "fotografia", "ilustracion", "visual"),
    "foto": ("fotografia", "imagen", "visual"),
    "curso": ("tutorial", "clase", "leccion", "aprendizaje"),
    "tutorial": ("curso", "clase", "leccion"),
    "plantilla": ("template", "modelo", "base"),
    "template": ("plantilla", "modelo"),
    "musica": ("audio", "pista", "sonido"),
    "audio": ("musica", "pista", "sonido"),
    "libro": ("ebook", "lectura", "publicacion"),
    "ebook": ("libro", "lectura"),
    "juego": ("videojuego", "entretenimiento"),
    "software": ("herramienta", "aplicacion", "app"),
}

_MAX_LONGITUD_Q = 120
_SEPARADOR = re.compile(r"[^0-9a-z]+")


def normalize_text(value: object) -> str:
    """Minúsculas, sin acentos y sin puntuación; apto para el índice y la q."""

    text = "" if value is None else str(value)
    decomposed = unicodedata.normalize("NFD", text.casefold())
    without_marks = "".join(
        character for character in decomposed if unicodedata.category(character) != "Mn"
    )
    return " ".join(_SEPARADOR.sub(" ", without_marks).split())


def tokenize(value: object) -> tuple[str, ...]:
    return tuple(token for token in normalize_text(value).split() if token)


def synonyms_for(token: str) -> tuple[str, ...]:
    """Sinónimos directos e inversos de un token ya normalizado."""

    found = list(SINONIMOS.get(token, ()))
    for canonical, terms in SINONIMOS.items():
        if token in terms and canonical not in found:
            found.append(canonical)
        if canonical not in found:
            found.extend(term for term in terms if term in token or token in term)
    # Deduplica conservando orden para que el índice sea determinista.
    return tuple(dict.fromkeys(found))


@dataclass(frozen=True)
class SearchTerms:
    """Términos originales y grupos expandidos con sinónimos."""

    original: tuple[str, ...]
    groups: tuple[tuple[str, ...], ...]

    @property
    def all_terms(self) -> tuple[str, ...]:
        todos: list[str] = []
        for group in self.groups:
            for term in group:
                if term not in todos:
                    todos.append(term)
        return tuple(todos)

    @property
    def is_empty(self) -> bool:
        return not self.original


def build_search_terms(query: str) -> SearchTerms:
    original = tokenize(query)
    groups = tuple(
        tuple(dict.fromkeys((token, *synonyms_for(token)))) for token in original
    )
    return SearchTerms(original=original, groups=groups)


def levenshtein(left: str, right: str, *, max_distance: int = 2) -> int:
    """Distancia de edición con corte temprano (barato para textos cortos)."""

    if left == right:
        return 0
    if abs(len(left) - len(right)) > max_distance:
        return max_distance + 1
    previous = list(range(len(right) + 1))
    for row, character in enumerate(left, start=1):
        current = [row]
        best = row
        for column, other in enumerate(right, start=1):
            cost = 0 if character == other else 1
            current.append(
                min(previous[column] + 1, current[column - 1] + 1, previous[column - 1] + cost)
            )
            best = min(best, current[column])
        if best > max_distance:
            return max_distance + 1
        previous = current
    return previous[-1]


def token_matches(token: str, candidate: str) -> bool:
    """Coincidencia exacta, por prefijo o con 1-2 errores de tecleo."""

    if token == candidate:
        return True
    if len(token) >= 3 and (candidate.startswith(token) or token.startswith(candidate)):
        return True
    tolerance = 2 if len(token) >= 7 else 1
    return levenshtein(token, candidate, max_distance=tolerance) <= tolerance


def text_matches(terms: SearchTerms, text: str) -> bool:
    """Todos los términos de la consulta deben aparecer (directos o sinónimos)."""

    if terms.is_empty:
        return True
    candidates = tokenize(text)
    for group in terms.groups:
        if not any(token_matches(term, candidate) for term in group for candidate in candidates):
            return False
    return True


def relevance_score(terms: SearchTerms, name: str, searchable_text: str) -> int:
    """Puntaje determinista: coincidencias en el nombre pesan el doble."""

    if terms.is_empty:
        return 0
    name_tokens = tokenize(name)
    text_tokens = tokenize(searchable_text)
    score = 0
    for group in terms.groups:
        term = group[0]
        exact_name = any(term == token for token in name_tokens)
        exact_text = any(term == token for token in text_tokens)
        synonym = any(
            sinonimo in text_tokens or sinonimo in name_tokens for sinonimo in group[1:]
        )
        fuzzy = any(token_matches(term, token) for token in text_tokens)
        if exact_name:
            score += 6
        elif exact_text:
            score += 4
        elif synonym:
            score += 2
        elif fuzzy:
            score += 1
    return score


@dataclass(frozen=True)
class ProductQuery:
    """Consulta ya validada que recibe el repositorio."""

    q: str = ""
    categoria: str | None = None
    edad: int | None = None
    precio_min: int | None = None
    precio_max: int | None = None
    orden: str = ORDEN_RELEVANCIA
    pagina: int = 1
    tamanio_pagina: int = 20

    @property
    def terms(self) -> SearchTerms:
        return build_search_terms(self.q)

    @property
    def offset(self) -> int:
        return (self.pagina - 1) * self.tamanio_pagina


def _entero(value: object, campo: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidCatalogQueryError(
            f"El filtro {campo} debe ser un entero.",
            details={"campo": campo, "valor": value, "codigo": "catalogo"},
        )
    return value


def validate_query(
    *,
    q: str | None,
    categoria: str | None,
    edad: int | None,
    precio_min: int | None,
    precio_max: int | None,
    orden: str | None,
    pagina: int,
    tamanio_pagina: int,
    max_age: int,
    min_price: int,
    max_page_size: int,
    known_categories: frozenset[str] | set[str],
) -> ProductQuery:
    """Valida CAT-01/CAT-03, categoría, orden y paginación con límite máximo."""

    texto = (q or "").strip()
    if len(texto) > _MAX_LONGITUD_Q:
        raise InvalidCatalogQueryError(
            f"El término de búsqueda no puede superar {_MAX_LONGITUD_Q} caracteres.",
            details={"campo": "q", "longitud": len(texto)},
        )

    categoria_limpia = categoria.strip() if categoria else None
    if categoria_limpia and categoria_limpia not in known_categories:
        raise InvalidCatalogQueryError(
            "La categoría del filtro no existe o no está activa.",
            details={"campo": "categoria", "valor": categoria_limpia},
        )

    edad_limpia = None
    if edad is not None:
        edad_limpia = _entero(edad, "edad")
        if edad_limpia < 0 or edad_limpia > max_age:
            raise InvalidCatalogQueryError(
                f"La edad del filtro CAT-03 debe estar entre 0 y {max_age}.",
                details={"campo": "edad", "valor": edad_limpia, "maximo": max_age},
            )

    limpio_min = None
    limpio_max = None
    if precio_min is not None:
        limpio_min = _entero(precio_min, "precioMin")
        if limpio_min < min_price:
            raise InvalidCatalogQueryError(
                f"El precio mínimo CAT-01 es {min_price} COP.",
                details={"campo": "precioMin", "valor": limpio_min, "minimo": min_price},
            )
    if precio_max is not None:
        limpio_max = _entero(precio_max, "precioMax")
        if limpio_max < min_price:
            raise InvalidCatalogQueryError(
                f"El precio máximo CAT-01 es {min_price} COP.",
                details={"campo": "precioMax", "valor": limpio_max, "minimo": min_price},
            )
    if limpio_min is not None and limpio_max is not None and limpio_min > limpio_max:
        raise InvalidCatalogQueryError(
            "El precio mínimo no puede ser mayor que el máximo.",
            details={"precioMin": limpio_min, "precioMax": limpio_max},
        )

    orden_limpio = (orden or ORDEN_RELEVANCIA).strip().lower()
    orden_normalizado = _ALIAS_ORDEN.get(orden_limpio)
    if orden_normalizado is None:
        raise InvalidCatalogQueryError(
            "El orden solicitado no es válido.",
            details={"campo": "orden", "valor": orden, "permitidos": list(ORDENES_PERMITIDOS)},
        )

    pagina_limpia = _entero(pagina, "pagina")
    tamanio_limpio = _entero(tamanio_pagina, "tamanioPagina")
    if pagina_limpia < 1:
        raise InvalidCatalogQueryError(
            "La página debe ser mayor o igual que 1.",
            details={"campo": "pagina", "valor": pagina_limpia},
        )
    if tamanio_limpio < 1 or tamanio_limpio > max_page_size:
        raise InvalidCatalogQueryError(
            f"El tamaño de página debe estar entre 1 y {max_page_size}.",
            details={
                "campo": "tamanioPagina",
                "valor": tamanio_limpio,
                "maximo": max_page_size,
            },
        )

    return ProductQuery(
        q=texto,
        categoria=categoria_limpia,
        edad=edad_limpia,
        precio_min=limpio_min,
        precio_max=limpio_max,
        orden=orden_normalizado,
        pagina=pagina_limpia,
        tamanio_pagina=tamanio_limpio,
    )


def indexable_text(
    *,
    nombre: str,
    descripcion: str,
    autor: str,
    categorias: list[str],
    category_names: list[str] | None = None,
) -> str:
    """Texto normalizado guardado en el índice (incluye sinónimos)."""

    base = normalize_text(
        " ".join([nombre, descripcion, autor, *categorias, *(category_names or [])])
    )
    tokens = base.split()
    extra: list[str] = []
    for token in tokens:
        extra.extend(synonyms_for(token))
    return " ".join(dict.fromkeys([*tokens, *extra]))
