"""Catálogo, validaciones y dependencias de los parámetros de autenticación.

HU-06 (FUN-16 / PRC-16). Los códigos ``AUT-xx`` son la clave pública del
parámetro; ``setting_field`` indica qué campo de :class:`Settings` consume el
valor vigente. El dominio no conoce HTTP ni SQLite.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal, Mapping, Protocol, runtime_checkable

AUTH_MODULO: Final = "autenticacion"
AUTH_PARAMETERS_ENTITY: Final = "parametros_autenticacion"
AUTH_PARAMETERS_WRITE_SCOPE: Final = "admin.auth.parameters.write"

INTENTOS_FALLIDOS = "AUT-01"
LONGITUD_CONTRASENA = "AUT-02"
TTL_ACCESO = "AUT-03"
TTL_REFRESCO = "AUT-04"
TTL_VERIFICACION = "AUT-05"
BLOQUEO_CUENTA = "AUT-06"
TTL_RECUPERACION = "AUT-07"


@dataclass(frozen=True)
class ParameterValidation:
    """Rango y tipo admitidos por un parámetro."""

    tipo: Literal["entero"] = "entero"
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
    """Restricción entre dos parámetros del mismo módulo."""

    codigo: str
    operador: Literal["<=", ">="]
    referencia: str
    factor_referencia: int = 1
    mensaje: str = ""

    def descripcion(self) -> str:
        return self.mensaje or f"{self.codigo} {self.operador} {self.referencia}"


@dataclass(frozen=True)
class AuthParameterDefinition:
    codigo: str
    nombre: str
    descripcion: str
    setting_field: str
    valor_default: int
    validacion: ParameterValidation
    dependencias: tuple[DependencyRule, ...] = ()
    modulo: str = AUTH_MODULO

    def validar_valor(self, valor: Any) -> None:
        """Rechaza tipos y rangos inválidos (``bool`` no cuenta como entero)."""

        from app.domain.exceptions import InvalidAuthParameterError

        if self.validacion.tipo == "entero":
            if isinstance(valor, bool) or not isinstance(valor, int):
                raise InvalidAuthParameterError(
                    f"El parámetro {self.codigo} debe ser un número entero.",
                    details={
                        "errores": [
                            {
                                "codigo": self.codigo,
                                "valor": valor,
                                "motivo": "tipo_invalido",
                                "esperado": self.validacion.tipo,
                            }
                        ]
                    },
                )
            minimo, maximo = self.validacion.minimo, self.validacion.maximo
            if (minimo is not None and valor < minimo) or (
                maximo is not None and valor > maximo
            ):
                raise InvalidAuthParameterError(
                    f"El parámetro {self.codigo} está fuera del rango permitido.",
                    details={
                        "errores": [
                            {
                                "codigo": self.codigo,
                                "valor": valor,
                                "motivo": "fuera_de_rango",
                                "minimo": minimo,
                                "maximo": maximo,
                            }
                        ]
                    },
                )

    def as_dict(self, valor: int) -> dict[str, Any]:
        return {
            "codigo": self.codigo,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "modulo": self.modulo,
            "valor": valor,
            "tipo": self.validacion.tipo,
            "validacion": self.validacion.as_dict(),
            "dependencias": [regla.descripcion() for regla in self.dependencias],
        }


PARAMETROS_AUTENTICACION: tuple[AuthParameterDefinition, ...] = (
    AuthParameterDefinition(
        codigo=INTENTOS_FALLIDOS,
        nombre="Intentos fallidos máximos",
        descripcion="Intentos de inicio de sesión fallidos antes de bloquear la cuenta.",
        setting_field="max_failed_login_attempts",
        valor_default=5,
        validacion=ParameterValidation(minimo=3, maximo=10),
    ),
    AuthParameterDefinition(
        codigo=LONGITUD_CONTRASENA,
        nombre="Longitud mínima de contraseña",
        descripcion="Cantidad mínima de caracteres exigida al crear o resetear contraseñas.",
        setting_field="password_min_length",
        valor_default=8,
        validacion=ParameterValidation(minimo=8, maximo=64),
    ),
    AuthParameterDefinition(
        codigo=TTL_ACCESO,
        nombre="Vigencia del token de acceso",
        descripcion="Minutos de validez del token de acceso emitido al iniciar sesión.",
        setting_field="access_token_ttl_minutes",
        valor_default=15,
        validacion=ParameterValidation(minimo=5, maximo=1440),
        dependencias=(
            DependencyRule(
                codigo=TTL_ACCESO,
                operador="<=",
                referencia=TTL_REFRESCO,
                factor_referencia=1440,
                mensaje="AUT-03 no puede superar AUT-04 expresado en minutos.",
            ),
        ),
    ),
    AuthParameterDefinition(
        codigo=TTL_REFRESCO,
        nombre="Vigencia del token de refresco",
        descripcion="Días de validez del token de refresco de la sesión.",
        setting_field="refresh_token_ttl_days",
        valor_default=7,
        validacion=ParameterValidation(minimo=1, maximo=90),
    ),
    AuthParameterDefinition(
        codigo=TTL_VERIFICACION,
        nombre="Vigencia del token de verificación",
        descripcion="Minutos de validez del enlace de verificación de correo.",
        setting_field="verification_token_ttl_minutes",
        valor_default=15,
        validacion=ParameterValidation(minimo=5, maximo=1440),
        dependencias=(
            DependencyRule(
                codigo=TTL_VERIFICACION,
                operador="<=",
                referencia=TTL_RECUPERACION,
                mensaje="AUT-05 no puede superar AUT-07 (verificación vs. recuperación).",
            ),
        ),
    ),
    AuthParameterDefinition(
        codigo=BLOQUEO_CUENTA,
        nombre="Duración del bloqueo",
        descripcion="Minutos que permanece bloqueada una cuenta tras agotar los intentos.",
        setting_field="account_lock_minutes",
        valor_default=15,
        validacion=ParameterValidation(minimo=5, maximo=60),
    ),
    AuthParameterDefinition(
        codigo=TTL_RECUPERACION,
        nombre="Vigencia del token de recuperación",
        descripcion="Minutos de validez del enlace de restablecimiento de contraseña.",
        setting_field="password_reset_ttl_minutes",
        valor_default=30,
        validacion=ParameterValidation(minimo=5, maximo=1440),
    ),
)

DEFINICIONES_POR_CODIGO: Final[Mapping[str, AuthParameterDefinition]] = {
    definicion.codigo: definicion for definicion in PARAMETROS_AUTENTICACION
}
SETTING_FIELD_BY_CODE: Final[Mapping[str, str]] = {
    definicion.codigo: definicion.setting_field
    for definicion in PARAMETROS_AUTENTICACION
}

# Códigos de otros submódulos: se rechazan explícitamente para que un módulo no
# pueda modificar la parametrización de otro aunque el actor sea administrador.
PREFIJOS_MODULOS_AJENOS: Final[Mapping[str, str]] = {
    "CAT-": "catalogo",
    "PROD-": "productos",
}


@dataclass(frozen=True)
class AuthParameterVersion:
    """Fila inmutable del historial de parametrización."""

    version: int
    vigente_desde: datetime
    modulo: str
    valores: dict[str, int]
    anteriores: dict[str, int]
    actor_id: str
    actor_roles: tuple[str, ...]
    motivo: str = ""

    def snapshot(self) -> AuthParameterSnapshot:
        return AuthParameterSnapshot(
            version=self.version,
            vigente_desde=self.vigente_desde,
            valores=dict(self.valores),
            modulo=self.modulo,
        )


@dataclass(frozen=True)
class AuthParameterSnapshot:
    """Valor vigente de los parámetros, asociado a una versión de caché."""

    version: int
    vigente_desde: datetime
    valores: dict[str, int]
    modulo: str = AUTH_MODULO

    def value(self, codigo: str) -> int:
        return self.valores[codigo]


@runtime_checkable
class AuthParametersProvider(Protocol):
    """Contrato mínimo consumido por las funciones de autenticación."""

    def value(self, codigo: str) -> int: ...


def validar_dependencias(valores: Mapping[str, Any]) -> list[str]:
    """Devuelve los mensajes de las dependencias incumplidas."""

    from app.domain.exceptions import InvalidAuthParameterError

    errores: list[str] = []
    for definicion in PARAMETROS_AUTENTICACION:
        for regla in definicion.dependencias:
            actual = valores.get(regla.codigo)
            referencia = valores.get(regla.referencia)
            if actual is None or referencia is None:
                continue
            limite = referencia * regla.factor_referencia
            if regla.operador == "<=" and actual > limite:
                errores.append(regla.descripcion())
            elif regla.operador == ">=" and actual < limite:
                errores.append(regla.descripcion())
    if errores:
        raise InvalidAuthParameterError(
            "Los valores propuestos incumplen dependencias entre parámetros.",
            details={"errores": [{"motivo": "dependencia", "mensaje": mensaje} for mensaje in errores]},
        )
    return errores


def valores_iniciales(settings: Any) -> dict[str, int]:
    """Toma los valores de ``Settings`` como versión 1 sin alterar el arranque."""

    valores: dict[str, int] = {}
    for definicion in PARAMETROS_AUTENTICACION:
        candidato = getattr(settings, definicion.setting_field, definicion.valor_default)
        try:
            definicion.validar_valor(candidato)
        except Exception:
            candidato = definicion.valor_default
        valores[definicion.codigo] = candidato
    try:
        validar_dependencias(valores)
    except Exception:
        valores = {
            definicion.codigo: definicion.valor_default
            for definicion in PARAMETROS_AUTENTICACION
        }
    return valores
