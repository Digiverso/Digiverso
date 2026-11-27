"""Dominio de la parametrización de comunidad (HU-21, FUN-64 / PRC-64).

Los códigos ``COMU-xx`` son la clave pública del parámetro y ``setting_field``
indica qué campo consumen las funciones de reseñas, seguimiento, feed,
recomendaciones y notificaciones de comunidad. El dominio no conoce HTTP,
SQLite ni la implementación de esos módulos, por lo que puede fusionarse con
HU-18, HU-19 y HU-20 sin importar sus servicios.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal, Mapping, Protocol, runtime_checkable

COMMUNITY_MODULO: Final = "comunidad"
COMMUNITY_PARAMETERS_ENTITY: Final = "parametros_comunidad"
COMMUNITY_PARAMETERS_WRITE_SCOPE: Final = "admin.community.parameters.write"

CALIFICACION_MINIMA = "COMU-01"
LONGITUD_MAXIMA_RESENA = "COMU-02"
RESENA_UNICA = "COMU-03"
REQUIERE_COMPRA = "COMU-04"
MAX_SEGUIDOS = "COMU-05"
MAX_TAMANIO_PAGINA = "COMU-07"
MAX_INTERESES = "COMU-08"
MAX_RECOMENDACIONES = "COMU-09"
DIAS_NOVEDAD = "COMU-10"
NOTIFICACIONES_ACTIVAS = "COMU-11"


@dataclass(frozen=True)
class ParameterValidation:
    """Tipo y rango admitidos por un parámetro de comunidad."""

    tipo: Literal["entero", "booleano"] = "entero"
    minimo: int | None = None
    maximo: int | None = None
    requerido: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "tipo": self.tipo,
            "minimo": self.minimo,
            "maximo": self.maximo,
            "requerido": self.requerido,
        }


@dataclass(frozen=True)
class DependencyRule:
    """Restricción de un parámetro contra un valor fijo."""

    codigo: str
    operador: Literal[">=", "<=", "=="]
    valor: Any
    mensaje: str

    def descripcion(self) -> str:
        return self.mensaje


@dataclass(frozen=True)
class CommunityParameterDefinition:
    codigo: str
    nombre: str
    descripcion: str
    setting_field: str
    valor_default: Any
    validacion: ParameterValidation
    dependencias: tuple[DependencyRule, ...] = ()
    modulo: str = COMMUNITY_MODULO
    # Nombres alternativos usados por dataclasses de otras HU de comunidad.
    aliases: tuple[str, ...] = ()

    def validar_valor(self, valor: Any) -> Any:
        """Valida tipo/rango y devuelve el valor normalizado que se persiste."""

        from app.domain.community_parameter_exceptions import (
            InvalidCommunityParameterError,
        )

        def rechazar(motivo: str, **extra: Any) -> None:
            raise InvalidCommunityParameterError(
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
        if tipo == "booleano":
            if not isinstance(valor, bool):
                rechazar("tipo_invalido", esperado=tipo)
            return valor

        if isinstance(valor, bool) or not isinstance(valor, int):
            rechazar("tipo_invalido", esperado=tipo)
        minimo, maximo = self.validacion.minimo, self.validacion.maximo
        if (minimo is not None and valor < minimo) or (
            maximo is not None and valor > maximo
        ):
            rechazar("fuera_de_rango", minimo=minimo, maximo=maximo)
        return valor

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


PARAMETROS_COMUNIDAD: tuple[CommunityParameterDefinition, ...] = (
    CommunityParameterDefinition(
        codigo=CALIFICACION_MINIMA,
        nombre="Calificación mínima de una reseña",
        descripcion="Calificación entera mínima admitida al reseñar un producto.",
        setting_field="community_rating_min",
        valor_default=1,
        validacion=ParameterValidation(minimo=1, maximo=5),
    ),
    CommunityParameterDefinition(
        codigo=LONGITUD_MAXIMA_RESENA,
        nombre="Longitud máxima del texto de una reseña",
        descripcion="Cantidad máxima de caracteres del texto saneado de una reseña.",
        setting_field="community_text_max_length",
        valor_default=1000,
        validacion=ParameterValidation(minimo=100, maximo=2000),
    ),
    CommunityParameterDefinition(
        codigo=RESENA_UNICA,
        nombre="Una reseña por usuario y producto",
        descripcion="Si está activo, un usuario solo puede reseñar una vez cada producto.",
        setting_field="community_unique_review",
        valor_default=True,
        validacion=ParameterValidation(tipo="booleano"),
    ),
    CommunityParameterDefinition(
        codigo=REQUIERE_COMPRA,
        nombre="Reseñas solo con compra acreditada",
        descripcion="Si está activo, se exige compra o licencia vigente para reseñar.",
        setting_field="community_require_purchase",
        valor_default=True,
        validacion=ParameterValidation(tipo="booleano"),
    ),
    CommunityParameterDefinition(
        codigo=MAX_SEGUIDOS,
        nombre="Máximo de usuarios seguidos",
        descripcion="Cantidad máxima de usuarios que un miembro puede seguir.",
        setting_field="community_max_following",
        valor_default=200,
        validacion=ParameterValidation(minimo=1, maximo=1000),
        aliases=("max_following",),
    ),
    CommunityParameterDefinition(
        codigo=MAX_TAMANIO_PAGINA,
        nombre="Tamaño máximo de página del feed",
        descripcion="Tamaño máximo de página admitido en feed, recomendaciones y listados.",
        setting_field="community_max_page_size",
        valor_default=100,
        validacion=ParameterValidation(minimo=1, maximo=500),
        aliases=("max_page_size",),
        dependencias=(
            DependencyRule(
                codigo=MAX_TAMANIO_PAGINA,
                operador=">=",
                valor=20,
                mensaje="COMU-07 no puede ser menor que el tamaño de página por defecto (20).",
            ),
        ),
    ),
    CommunityParameterDefinition(
        codigo=MAX_INTERESES,
        nombre="Máximo de categorías de interés",
        descripcion="Cantidad máxima de categorías que un usuario puede declarar como interés.",
        setting_field="community_max_interests",
        valor_default=10,
        validacion=ParameterValidation(minimo=1, maximo=50),
        aliases=("max_interests",),
    ),
    CommunityParameterDefinition(
        codigo=MAX_RECOMENDACIONES,
        nombre="Máximo de recomendaciones",
        descripcion="Cantidad máxima de recomendaciones devueltas por usuario.",
        setting_field="community_max_recommendations",
        valor_default=20,
        validacion=ParameterValidation(minimo=1, maximo=100),
        aliases=("max_recommendations",),
    ),
    CommunityParameterDefinition(
        codigo=DIAS_NOVEDAD,
        nombre="Ventana de novedad de las recomendaciones",
        descripcion="Días que una publicación se considera reciente al puntuar recomendaciones.",
        setting_field="community_recent_days",
        valor_default=30,
        validacion=ParameterValidation(minimo=1, maximo=365),
        aliases=("recent_days",),
    ),
    CommunityParameterDefinition(
        codigo=NOTIFICACIONES_ACTIVAS,
        nombre="Notificaciones de comunidad activas",
        descripcion="Interruptor global de las notificaciones por seguimiento y reseña.",
        setting_field="community_notifications_enabled",
        valor_default=True,
        validacion=ParameterValidation(tipo="booleano"),
    ),
)

DEFINICIONES_POR_CODIGO: Final[Mapping[str, CommunityParameterDefinition]] = {
    definicion.codigo: definicion for definicion in PARAMETROS_COMUNIDAD
}
CODIGO_BY_SETTING_FIELD: Final[Mapping[str, str]] = {
    definicion.setting_field: definicion.codigo for definicion in PARAMETROS_COMUNIDAD
}
CODIGO_BY_ALIAS: Final[Mapping[str, str]] = {
    alias: definicion.codigo
    for definicion in PARAMETROS_COMUNIDAD
    for alias in definicion.aliases
}

# Se rechazan explícitamente para que la comunidad no pueda alterar la
# parametrización ajena aunque el actor sea administrador.
MODULOS_AJENOS: Final[Mapping[str, str]] = {
    "AUT-": "autenticacion",
    "CAT-": "catalogo",
    "COM-": "comercio",
}


@dataclass(frozen=True)
class CommunityParameterVersion:
    """Fila inmutable del historial de parametrización de comunidad."""

    version: int
    vigente_desde: datetime
    modulo: str
    valores: dict[str, Any]
    anteriores: dict[str, Any]
    actor_id: str
    actor_roles: tuple[str, ...]
    motivo: str = ""

    def snapshot(self) -> CommunityParameterSnapshot:
        return CommunityParameterSnapshot(
            version=self.version,
            vigente_desde=self.vigente_desde,
            valores=dict(self.valores),
            modulo=self.modulo,
        )


@dataclass(frozen=True)
class CommunityParameterSnapshot:
    """Valor vigente de los parámetros, asociado a una versión de caché."""

    version: int
    vigente_desde: datetime
    valores: dict[str, Any]
    modulo: str = COMMUNITY_MODULO

    def value(self, codigo: str) -> Any:
        return self.valores[codigo]


@runtime_checkable
class CommunityParametersProvider(Protocol):
    """Contrato mínimo consumido por las funciones de comunidad."""

    def value(self, codigo: str) -> Any: ...


def validar_dependencias(valores: Mapping[str, Any]) -> list[str]:
    """Devuelve los mensajes incumplidos o lanza un error de validación."""

    from app.domain.community_parameter_exceptions import (
        InvalidCommunityParameterError,
    )

    errores: list[str] = []
    for definicion in PARAMETROS_COMUNIDAD:
        for regla in definicion.dependencias:
            actual = valores.get(regla.codigo)
            if actual is None:
                continue
            incumplida = (
                (regla.operador == ">=" and actual < regla.valor)
                or (regla.operador == "<=" and actual > regla.valor)
                or (regla.operador == "==" and actual != regla.valor)
            )
            if incumplida:
                errores.append(regla.descripcion())
    if errores:
        raise InvalidCommunityParameterError(
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
    for definicion in PARAMETROS_COMUNIDAD:
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
            for definicion in PARAMETROS_COMUNIDAD
        }
    return valores
