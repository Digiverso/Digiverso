"""Catálogo y reglas de los parámetros del módulo Comercio (HU-17).

FUN-53 / PRC-53. Los códigos ``COM-xx`` son la clave pública del parámetro;
``setting_field`` indica qué campo de :class:`Settings` consume el valor
vigente. El dominio no conoce HTTP ni SQLite.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal, Mapping, Protocol, runtime_checkable

COMMERCE_MODULO: Final = "comercio"
COMMERCE_PARAMETERS_ENTITY: Final = "parametros_comercio"
COMMERCE_PARAMETERS_WRITE_SCOPE: Final = "admin.commerce.parameters.write"

# Códigos públicos. Los valores iniciales coinciden con los definidos para
# HU-15/HU-16 en ``Settings``; si esos campos no existen aún se usa el valor
# por defecto de esta tabla.
COMISION = "COM-01"
NETO_PRODUCTOR = "COM-02"
MONEDA = "COM-03"
TTL_DESCARGA = "COM-08"
MAX_DESCARGAS = "COM-09"
DIAS_LIQUIDACION = "COM-10"
MINIMO_LIQUIDACION = "COM-11"

PORCENTAJE_ESPERADO: Final = 100


@dataclass(frozen=True)
class ParameterValidation:
    """Tipo, rango y valores admitidos por un parámetro."""

    tipo: Literal["entero", "texto"] = "entero"
    minimo: int | None = None
    maximo: int | None = None
    requerido: bool = True
    permitidos: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "tipo": self.tipo,
            "minimo": self.minimo,
            "maximo": self.maximo,
            "requerido": self.requerido,
            "permitidos": list(self.permitidos),
        }


@dataclass(frozen=True)
class BusinessRule:
    """Regla que involucra a varios parámetros del módulo."""

    codigo: str
    mensaje: str

    def descripcion(self) -> str:
        return self.mensaje


@dataclass(frozen=True)
class CommerceParameterDefinition:
    codigo: str
    nombre: str
    descripcion: str
    setting_field: str
    valor_default: Any
    validacion: ParameterValidation
    dependencias: tuple[BusinessRule, ...] = ()
    modulo: str = COMMERCE_MODULO

    def validar_valor(self, valor: Any) -> Any:
        """Valida tipo/rango y devuelve el valor normalizado que se persiste."""

        from app.domain.commerce_parameter_exceptions import (
            InvalidCommerceParameterError,
        )

        def rechazar(motivo: str, **extra: Any) -> None:
            raise InvalidCommerceParameterError(
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

        if not isinstance(valor, str):
            rechazar("tipo_invalido", esperado=tipo)
        normalizado = valor.strip().upper()
        if self.validacion.requerido and not normalizado:
            rechazar("vacio")
        if self.validacion.permitidos and normalizado not in self.validacion.permitidos:
            rechazar("valor_no_permitido", permitidos=list(self.validacion.permitidos))
        return normalizado

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


_REGLA_PORCENTAJES = BusinessRule(
    codigo=COMISION,
    mensaje=(
        f"{COMISION} (comisión) y {NETO_PRODUCTOR} (neto al productor) "
        "deben sumar 100 %."
    ),
)

PARAMETROS_COMERCIO: tuple[CommerceParameterDefinition, ...] = (
    CommerceParameterDefinition(
        codigo=COMISION,
        nombre="Porcentaje de comisión de la plataforma",
        descripcion="Comisión de Comercio retenida sobre cada venta pagada.",
        setting_field="commerce_commission_percentage",
        valor_default=15,
        validacion=ParameterValidation(minimo=0, maximo=100),
        dependencias=(_REGLA_PORCENTAJES,),
    ),
    CommerceParameterDefinition(
        codigo=NETO_PRODUCTOR,
        nombre="Porcentaje neto del productor",
        descripcion="Porción de la venta que se liquida al productor.",
        setting_field="commerce_producer_percentage",
        valor_default=85,
        validacion=ParameterValidation(minimo=0, maximo=100),
        dependencias=(_REGLA_PORCENTAJES,),
    ),
    CommerceParameterDefinition(
        codigo=MONEDA,
        nombre="Moneda de las ventas y liquidaciones",
        descripcion="Moneda en la que se expresan montos, comisiones y liquidaciones.",
        setting_field="commerce_currency",
        valor_default="COP",
        validacion=ParameterValidation(tipo="texto", permitidos=("COP",)),
    ),
    CommerceParameterDefinition(
        codigo=TTL_DESCARGA,
        nombre="Vigencia de la URL de descarga",
        descripcion="Minutos de validez de la URL firmada de descarga.",
        setting_field="commerce_download_ttl_minutes",
        valor_default=10,
        validacion=ParameterValidation(minimo=1, maximo=1440),
    ),
    CommerceParameterDefinition(
        codigo=MAX_DESCARGAS,
        nombre="Máximo de descargas por URL",
        descripcion="Cantidad de descargas permitidas antes de vencer la URL firmada.",
        setting_field="commerce_max_downloads",
        valor_default=3,
        validacion=ParameterValidation(minimo=1, maximo=100),
    ),
    CommerceParameterDefinition(
        codigo=DIAS_LIQUIDACION,
        nombre="Días para la liquidación",
        descripcion="Días transcurridos desde la venta hasta que sea liquidable.",
        setting_field="commerce_payout_days",
        valor_default=15,
        validacion=ParameterValidation(minimo=1, maximo=90),
    ),
    CommerceParameterDefinition(
        codigo=MINIMO_LIQUIDACION,
        nombre="Mínimo a liquidar",
        descripcion="Monto mínimo acumulado para generar una liquidación.",
        setting_field="commerce_payout_minimum",
        valor_default=50000,
        validacion=ParameterValidation(minimo=0, maximo=100_000_000),
    ),
)

DEFINICIONES_POR_CODIGO: Final[Mapping[str, CommerceParameterDefinition]] = {
    definicion.codigo: definicion for definicion in PARAMETROS_COMERCIO
}
SETTING_FIELD_BY_CODE: Final[Mapping[str, str]] = {
    definicion.codigo: definicion.setting_field for definicion in PARAMETROS_COMERCIO
}
CODIGO_BY_SETTING_FIELD: Final[Mapping[str, str]] = {
    definicion.setting_field: definicion.codigo for definicion in PARAMETROS_COMERCIO
}

# Otros módulos: se rechazan explícitamente para que Comercio no pueda
# modificar la parametrización ajena aunque el actor sea administrador.
MODULOS_AJENOS: Final[Mapping[str, str]] = {
    "AUT-": "autenticacion",
    "CAT-": "catalogo",
    "COMU-": "comunidad",
}


@dataclass(frozen=True)
class CommerceParameterVersion:
    """Fila inmutable del historial de parametrización de comercio."""

    version: int
    vigente_desde: datetime
    modulo: str
    valores: dict[str, Any]
    anteriores: dict[str, Any]
    actor_id: str
    actor_roles: tuple[str, ...]
    motivo: str = ""

    def snapshot(self) -> CommerceParameterSnapshot:
        return CommerceParameterSnapshot(
            version=self.version,
            vigente_desde=self.vigente_desde,
            valores=dict(self.valores),
            modulo=self.modulo,
        )


@dataclass(frozen=True)
class CommerceParameterSnapshot:
    """Valor vigente de los parámetros, asociado a una versión de caché."""

    version: int
    vigente_desde: datetime
    valores: dict[str, Any]
    modulo: str = COMMERCE_MODULO

    def value(self, codigo: str) -> Any:
        return self.valores[codigo]


@runtime_checkable
class CommerceParametersProvider(Protocol):
    """Contrato mínimo consumido por las funciones de comercio."""

    def value(self, codigo: str) -> Any: ...


def validar_porcentajes(valores: Mapping[str, Any]) -> list[str]:
    """Verifica que ``COM-01 + COM-02`` sea exactamente 100 %."""

    from app.domain.commerce_parameter_exceptions import (
        InvalidCommerceParameterError,
    )

    comision = valores.get(COMISION)
    neto = valores.get(NETO_PRODUCTOR)
    if comision is None or neto is None:
        return []

    suma = int(comision) + int(neto)
    if suma != PORCENTAJE_ESPERADO:
        raise InvalidCommerceParameterError(
            "COM-01 y COM-02 deben sumar 100 %.",
            details={
                "errores": [
                    {
                        "motivo": "porcentajes",
                        "mensaje": _REGLA_PORCENTAJES.descripcion(),
                        "suma": suma,
                        "esperado": PORCENTAJE_ESPERADO,
                    }
                ],
                "codigos": [COMISION, NETO_PRODUCTOR],
            },
        )
    return []


def validar_reglas_negocio(valores: Mapping[str, Any]) -> list[str]:
    """Devuelve los mensajes de las reglas incumplidas (o lanza 400)."""

    mensajes = validar_porcentajes(valores)
    return mensajes


def valores_iniciales(settings: Any) -> dict[str, Any]:
    """Toma los valores de ``Settings`` como versión 1 sin alterar el arranque."""

    valores: dict[str, Any] = {}
    for definicion in PARAMETROS_COMERCIO:
        candidato = getattr(settings, definicion.setting_field, definicion.valor_default)
        try:
            valores[definicion.codigo] = definicion.validar_valor(candidato)
        except Exception:
            valores[definicion.codigo] = definicion.validar_valor(definicion.valor_default)
    try:
        validar_reglas_negocio(valores)
    except Exception:
        valores = {
            definicion.codigo: definicion.validar_valor(definicion.valor_default)
            for definicion in PARAMETROS_COMERCIO
        }
    return valores
