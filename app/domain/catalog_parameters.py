"""Catálogo, validaciones y dependencias de los parámetros del módulo Catálogo.

HU-13 (FUN-39 / PRC-39). Los códigos ``CAT-xx`` son la clave pública del
parámetro; ``setting_field`` indica qué campo de :class:`Settings` consume el
valor vigente. El dominio no conoce HTTP ni SQLite.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal, Mapping, Protocol, runtime_checkable

CATALOG_MODULO: Final = "catalogo"
CATALOG_PARAMETERS_ENTITY: Final = "parametros_catalogo"
CATALOG_PARAMETERS_WRITE_SCOPE: Final = "admin.catalog.parameters.write"

PRECIO_MINIMO = "CAT-01"
MONEDA = "CAT-02"
MAX_EDAD = "CAT-03"
FORMATOS_IMAGEN = "CAT-05"
MAX_BYTES_IMAGEN = "CAT-06"
FORMATOS_VIDEO = "CAT-07"
MAX_BYTES_VIDEO = "CAT-08"
MIN_IMAGENES = "CAT-09"
MAX_MEDIOS = "CAT-10"
MAX_LONGITUD_NOMBRE = "CAT-11"
MAX_LONGITUD_DESCRIPCION = "CAT-12"
MAX_CATEGORIAS = "CAT-13"
DIAS_SUSPENSION = "CAT-16"
MAX_LONGITUD_CATEGORIA = "CAT-17"

_MIB = 1024 * 1024


@dataclass(frozen=True)
class ParameterValidation:
    """Tipo, rango y valores admitidos por un parámetro."""

    tipo: Literal["entero", "texto", "lista"] = "entero"
    minimo: int | None = None
    maximo: int | None = None
    requerido: bool = True
    permitidos: tuple[str, ...] = ()
    max_items: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "tipo": self.tipo,
            "minimo": self.minimo,
            "maximo": self.maximo,
            "requerido": self.requerido,
            "permitidos": list(self.permitidos),
            "maxItems": self.max_items,
        }


@dataclass(frozen=True)
class DependencyRule:
    """Restricción entre parámetros del catálogo o contra un valor fijo."""

    codigo: str
    operador: Literal["<=", ">=", "==", "disjunto"]
    mensaje: str
    referencia: str | None = None
    valor: Any = None
    factor_referencia: int = 1

    def descripcion(self) -> str:
        return self.mensaje


@dataclass(frozen=True)
class CatalogParameterDefinition:
    codigo: str
    nombre: str
    descripcion: str
    setting_field: str
    valor_default: Any
    validacion: ParameterValidation
    dependencias: tuple[DependencyRule, ...] = ()
    modulo: str = CATALOG_MODULO

    def validar_valor(self, valor: Any) -> Any:
        """Valida tipo/rango y devuelve el valor normalizado que se persiste."""

        from app.domain.catalog_parameter_exceptions import InvalidCatalogParameterError

        def rechazar(motivo: str, **extra: Any) -> None:
            raise InvalidCatalogParameterError(
                f"El parámetro {self.codigo} no es válido.",
                details={
                    "errores": [
                        {
                            "codigo": self.codigo,
                            "valor": valor,
                            "motivo": motivo,
                            **extra,
                        }
                    ]
                },
            )

        tipo = self.validacion.tipo
        if tipo == "entero":
            if isinstance(valor, bool) or not isinstance(valor, int):
                rechazar("tipo_invalido", esperado=tipo)
            minimo, maximo = self.validacion.minimo, self.validacion.maximo
            if (minimo is not None and valor < minimo) or (
                maximo is not None and valor > maximo
            ):
                rechazar("fuera_de_rango", minimo=minimo, maximo=maximo)
            return valor

        if tipo == "texto":
            if not isinstance(valor, str):
                rechazar("tipo_invalido", esperado=tipo)
            normalizado = valor.strip().upper()
            if self.validacion.requerido and not normalizado:
                rechazar("vacio")
            if self.validacion.permitidos and normalizado not in self.validacion.permitidos:
                rechazar("valor_no_permitido", permitidos=list(self.validacion.permitidos))
            return normalizado

        # tipo == "lista": formatos de imagen/video. Se guarda como lista para
        # que sea JSON serializable; la vista de Settings la convierte a tupla.
        if not isinstance(valor, (list, tuple)):
            rechazar("tipo_invalido", esperado=tipo)
        if self.validacion.requerido and not valor:
            rechazar("vacio")
        normalizados: list[str] = []
        for item in valor:
            if not isinstance(item, str) or not item.strip():
                rechazar("tipo_invalido", esperado="texto")
            candidato = item.strip().lower()
            if candidato in normalizados:
                rechazar("duplicado", valor=candidato)
            if self.validacion.permitidos and candidato not in self.validacion.permitidos:
                rechazar("valor_no_permitido", permitidos=list(self.validacion.permitidos))
            normalizados.append(candidato)
        if self.validacion.max_items is not None and len(normalizados) > self.validacion.max_items:
            rechazar("demasiados_valores", maximo=self.validacion.max_items)
        return normalizados

    def as_dict(self, valor: Any) -> dict[str, Any]:
        return {
            "codigo": self.codigo,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "modulo": self.modulo,
            "campo": self.setting_field,
            "valor": valor,
            "tipo": self.validacion.tipo,
            "validacion": self.validacion.as_dict(),
            "dependencias": [regla.descripcion() for regla in self.dependencias],
        }


PARAMETROS_CATALOGO: tuple[CatalogParameterDefinition, ...] = (
    CatalogParameterDefinition(
        codigo=PRECIO_MINIMO,
        nombre="Precio mínimo del producto",
        descripcion="Precio mínimo en COP exigido al crear o editar productos.",
        setting_field="product_min_price",
        valor_default=3500,
        validacion=ParameterValidation(minimo=3500, maximo=1_000_000),
        dependencias=(
            DependencyRule(
                codigo=MONEDA,
                operador="==",
                valor="COP",
                mensaje="CAT-01 (precio mínimo) solo se admite con CAT-02 = COP.",
            ),
        ),
    ),
    CatalogParameterDefinition(
        codigo=MONEDA,
        nombre="Moneda del catálogo",
        descripcion="Moneda en la que se expresan los precios del catálogo.",
        setting_field="product_currency",
        valor_default="COP",
        validacion=ParameterValidation(tipo="texto", permitidos=("COP",)),
    ),
    CatalogParameterDefinition(
        codigo=MAX_EDAD,
        nombre="Edad máxima",
        descripcion="Edad máxima admitida en productos y filtros de búsqueda.",
        setting_field="product_max_age",
        valor_default=99,
        validacion=ParameterValidation(minimo=1, maximo=120),
    ),
    CatalogParameterDefinition(
        codigo=FORMATOS_IMAGEN,
        nombre="Formatos de imagen permitidos",
        descripcion="Extensiones admitidas para imágenes de producto.",
        setting_field="media_image_formats",
        valor_default=("jpg", "png", "webp"),
        validacion=ParameterValidation(
            tipo="lista", permitidos=("jpg", "jpeg", "png", "webp"), max_items=6
        ),
        dependencias=(
            DependencyRule(
                codigo=FORMATOS_IMAGEN,
                operador="disjunto",
                referencia=FORMATOS_VIDEO,
                mensaje="CAT-05 y CAT-07 no pueden compartir formatos.",
            ),
        ),
    ),
    CatalogParameterDefinition(
        codigo=MAX_BYTES_IMAGEN,
        nombre="Tamaño máximo de imagen",
        descripcion="Bytes máximos permitidos por imagen.",
        setting_field="media_max_image_bytes",
        valor_default=10 * _MIB,
        validacion=ParameterValidation(minimo=1024, maximo=100 * _MIB),
        dependencias=(
            DependencyRule(
                codigo=MAX_BYTES_IMAGEN,
                operador="<=",
                referencia=MAX_BYTES_VIDEO,
                mensaje="CAT-06 no puede superar CAT-08.",
            ),
        ),
    ),
    CatalogParameterDefinition(
        codigo=FORMATOS_VIDEO,
        nombre="Formatos de video permitidos",
        descripcion="Extensiones admitidas para videos de producto.",
        setting_field="media_video_formats",
        valor_default=("mp4", "mov", "webm"),
        validacion=ParameterValidation(
            tipo="lista", permitidos=("mp4", "m4v", "mov", "webm"), max_items=6
        ),
    ),
    CatalogParameterDefinition(
        codigo=MAX_BYTES_VIDEO,
        nombre="Tamaño máximo de video",
        descripcion="Bytes máximos permitidos por video.",
        setting_field="media_max_video_bytes",
        valor_default=200 * _MIB,
        validacion=ParameterValidation(minimo=1024, maximo=500 * _MIB),
    ),
    CatalogParameterDefinition(
        codigo=MIN_IMAGENES,
        nombre="Mínimo de imágenes",
        descripcion="Cantidad mínima de imágenes para enviar un producto a revisión.",
        setting_field="product_min_images",
        valor_default=1,
        validacion=ParameterValidation(minimo=0, maximo=10),
        dependencias=(
            DependencyRule(
                codigo=MIN_IMAGENES,
                operador="<=",
                referencia=MAX_MEDIOS,
                mensaje="CAT-09 no puede superar CAT-10.",
            ),
        ),
    ),
    CatalogParameterDefinition(
        codigo=MAX_MEDIOS,
        nombre="Máximo de medios por producto",
        descripcion="Cantidad máxima de medios activos por producto.",
        setting_field="media_max_per_product",
        valor_default=10,
        validacion=ParameterValidation(minimo=1, maximo=50),
    ),
    CatalogParameterDefinition(
        codigo=MAX_LONGITUD_NOMBRE,
        nombre="Longitud máxima del nombre",
        descripcion="Cantidad máxima de caracteres del nombre de un producto.",
        setting_field="product_name_max_length",
        valor_default=120,
        validacion=ParameterValidation(minimo=2, maximo=200),
    ),
    CatalogParameterDefinition(
        codigo=MAX_LONGITUD_DESCRIPCION,
        nombre="Longitud máxima de la descripción",
        descripcion="Cantidad máxima de caracteres de la descripción de un producto.",
        setting_field="product_description_max_length",
        valor_default=2000,
        validacion=ParameterValidation(minimo=1, maximo=10_000),
    ),
    CatalogParameterDefinition(
        codigo=MAX_CATEGORIAS,
        nombre="Máximo de categorías por producto",
        descripcion="Cantidad máxima de categorías asignables a un producto.",
        setting_field="product_max_categories",
        valor_default=5,
        validacion=ParameterValidation(minimo=1, maximo=20),
    ),
    # CAT-16 y CAT-17 se declaran aquí para que la parametrización sea
    # compatible con HU-11/HU-12 cuando esas ramas se fusionen. Si el campo
    # aún no existe en Settings, ``valores_iniciales`` usa el valor por defecto.
    CatalogParameterDefinition(
        codigo=DIAS_SUSPENSION,
        nombre="Días de suspensión por sanción",
        descripcion="Duración por defecto de una suspensión temporal (HU-12).",
        setting_field="report_suspension_days",
        valor_default=7,
        validacion=ParameterValidation(minimo=1, maximo=90),
    ),
    CatalogParameterDefinition(
        codigo=MAX_LONGITUD_CATEGORIA,
        nombre="Longitud máxima del nombre de categoría",
        descripcion="Cantidad máxima de caracteres del nombre de una categoría (HU-11).",
        setting_field="category_name_max_length",
        valor_default=80,
        validacion=ParameterValidation(minimo=2, maximo=120),
    ),
)

DEFINICIONES_POR_CODIGO: Final[Mapping[str, CatalogParameterDefinition]] = {
    definicion.codigo: definicion for definicion in PARAMETROS_CATALOGO
}
SETTING_FIELD_BY_CODE: Final[Mapping[str, str]] = {
    definicion.codigo: definicion.setting_field for definicion in PARAMETROS_CATALOGO
}
CODIGO_BY_SETTING_FIELD: Final[Mapping[str, str]] = {
    definicion.setting_field: definicion.codigo for definicion in PARAMETROS_CATALOGO
}

# Otros módulos: se rechazan explícitamente para que el catálogo no pueda
# modificar la parametrización ajena aunque el actor sea administrador.
MODULOS_AJENOS: Final[Mapping[str, str]] = {
    "AUT-": "autenticacion",
    "COM-": "comercio",
    "COMU-": "comunidad",
}


@dataclass(frozen=True)
class CatalogParameterVersion:
    """Fila inmutable del historial de parametrización del catálogo."""

    version: int
    vigente_desde: datetime
    modulo: str
    valores: dict[str, Any]
    anteriores: dict[str, Any]
    actor_id: str
    actor_roles: tuple[str, ...]
    motivo: str = ""

    def snapshot(self) -> CatalogParameterSnapshot:
        return CatalogParameterSnapshot(
            version=self.version,
            vigente_desde=self.vigente_desde,
            valores=dict(self.valores),
            modulo=self.modulo,
        )


@dataclass(frozen=True)
class CatalogParameterSnapshot:
    """Valor vigente de los parámetros, asociado a una versión de caché."""

    version: int
    vigente_desde: datetime
    valores: dict[str, Any]
    modulo: str = CATALOG_MODULO

    def value(self, codigo: str) -> Any:
        return self.valores[codigo]


@runtime_checkable
class CatalogParametersProvider(Protocol):
    """Contrato mínimo consumido por las funciones del catálogo."""

    def value(self, codigo: str) -> Any: ...


def validar_dependencias(valores: Mapping[str, Any]) -> list[str]:
    """Devuelve los mensajes de las dependencias incumplidas (o lanza 400)."""

    from app.domain.catalog_parameter_exceptions import InvalidCatalogParameterError

    errores: list[str] = []
    for definicion in PARAMETROS_CATALOGO:
        for regla in definicion.dependencias:
            actual = valores.get(regla.codigo)
            referencia = (
                valores.get(regla.referencia) if regla.referencia else regla.valor
            )
            if actual is None or referencia is None:
                continue
            if regla.operador == "==" and actual != referencia:
                errores.append(regla.descripcion())
            elif regla.operador == "disjunto":
                if set(actual) & set(referencia):
                    errores.append(regla.descripcion())
            elif regla.operador == "<=" and actual > referencia * regla.factor_referencia:
                errores.append(regla.descripcion())
            elif regla.operador == ">=" and actual < referencia * regla.factor_referencia:
                errores.append(regla.descripcion())
    if errores:
        raise InvalidCatalogParameterError(
            "Los valores propuestos incumplen dependencias entre parámetros.",
            details={
                "errores": [
                    {"motivo": "dependencia", "mensaje": mensaje} for mensaje in errores
                ]
            },
        )
    return errores


def valores_iniciales(settings: Any) -> dict[str, Any]:
    """Toma los valores de ``Settings`` como versión 1 sin alterar el arranque."""

    valores: dict[str, Any] = {}
    for definicion in PARAMETROS_CATALOGO:
        candidato = getattr(settings, definicion.setting_field, definicion.valor_default)
        try:
            valores[definicion.codigo] = definicion.validar_valor(candidato)
        except Exception:
            valores[definicion.codigo] = definicion.validar_valor(definicion.valor_default)
    try:
        validar_dependencias(valores)
    except Exception:
        valores = {
            definicion.codigo: definicion.validar_valor(definicion.valor_default)
            for definicion in PARAMETROS_CATALOGO
        }
    return valores
