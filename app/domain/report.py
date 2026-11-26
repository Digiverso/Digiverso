"""Dominio de reportes y sanciones del catálogo (HU-12, SUB-13).

CAT-14 fija los motivos Documentados de reporte, CAT-15 los tipos de sanción
y CAT-16 la vigencia por defecto de una suspensión temporal. Las reglas se
validan aquí y no en los esquemas HTTP para que puedan reutilizarse desde
cualquier caso de uso.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from app.domain.exceptions import InvalidReportError, InvalidSanctionError

CAT_14 = "CAT-14"
CAT_15 = "CAT-15"
CAT_16 = "CAT-16"

ESTADO_ABIERTO = "abierto"
ESTADO_EN_REVISION = "en_revision"
ESTADO_RESUELTO = "resuelto"
ESTADOS_REPORTE = (ESTADO_ABIERTO, ESTADO_EN_REVISION, ESTADO_RESUELTO)
ESTADOS_PENDIENTES = frozenset({ESTADO_ABIERTO, ESTADO_EN_REVISION})

DECISION_DESIMISION = "desestimado"
DECISION_SANCION = "sancionado"
DECISIONES = (DECISION_DESIMISION, DECISION_SANCION)

TIPO_PRODUCTO = "producto"
TIPO_RESENA = "resena"
TIPO_USUARIO = "usuario"
TIPOS_CONTENIDO = (TIPO_PRODUCTO, TIPO_RESENA, TIPO_USUARIO)

MOTIVOS_PERMITIDOS: tuple[str, ...] = (
    "derechos_autor",
    "contenido_inseguro",
    "acoso",
    "spam",
    "fraude",
    "informacion_falsa",
    "edad_inadecuada",
    "autoria_no_verificada",
    "derechos_no_aclarados",
    "funciones_no_verificadas",
    "violencia",
    "discriminacion",
    "cat-14",
    "otro",
)

_ALIAS_MOTIVOS = {
    "derechos-de-autor": "derechos_autor",
    "derechosdeautor": "derechos_autor",
    "plagio": "derechos_autor",
    "seguridad": "contenido_inseguro",
    "contenido-inseguro": "contenido_inseguro",
    "informacion-falsa": "informacion_falsa",
    "edad-inadecuada": "edad_inadecuada",
    "autoria-no-verificada": "autoria_no_verificada",
    "derechos-no-aclarados": "derechos_no_aclarados",
    "funciones-no-verificadas": "funciones_no_verificadas",
}

TIPO_ADVERTENCIA = "advertencia"
TIPO_RESTRICCION = "restriccion_contenido"
TIPO_SUSPENSION = "suspension_temporal"
TIPO_BLOQUEO = "bloqueo_permanente"

TIPOS_SANCION: tuple[str, ...] = (
    TIPO_ADVERTENCIA,
    TIPO_RESTRICCION,
    TIPO_SUSPENSION,
    TIPO_BLOQUEO,
)

_ALIAS_TIPOS_SANCION = {
    "advertencia": TIPO_ADVERTENCIA,
    "aviso": TIPO_ADVERTENCIA,
    "warning": TIPO_ADVERTENCIA,
    "restriccion": TIPO_RESTRICCION,
    "restriccion-de-contenido": TIPO_RESTRICCION,
    "restriccion_contenido": TIPO_RESTRICCION,
    "restricciondecontenido": TIPO_RESTRICCION,
    "suspension": TIPO_SUSPENSION,
    "suspension-temporal": TIPO_SUSPENSION,
    "suspension_temporal": TIPO_SUSPENSION,
    "suspensiontemporal": TIPO_SUSPENSION,
    "suspencion_temporal": TIPO_SUSPENSION,
    "temporal": TIPO_SUSPENSION,
    "bloqueo": TIPO_BLOQUEO,
    "bloqueo-permanente": TIPO_BLOQUEO,
    "bloqueo_permanente": TIPO_BLOQUEO,
    "permanente": TIPO_BLOQUEO,
}

ACCION_ARCHIVAR = "archivar"
ACCION_RESTRINGIR = "restringir"
ACCIONES_CONTENIDO = (ACCION_ARCHIVAR, ACCION_RESTRINGIR)

EVENTO_REPORTE_CREADO = "report.created"
EVENTO_REPORTE_RESUELTO = "report.resolved"
EVENTO_SANCION_APLICADA = "sanction.applied"


def _clave(valor: object) -> str:
    """Normaliza guiones, espacios y mayúsculas para comparar identificadores."""

    return str(valor or "").strip().lower().replace(" ", "_").replace("-", "_")


def normalizar_motivo(valor: object) -> str:
    """Valida un motivo contra CAT-14 y devuelve su forma canónica."""

    texto = _clave(valor)
    texto = _ALIAS_MOTIVOS.get(texto, texto)
    if texto not in MOTIVOS_PERMITIDOS:
        raise InvalidReportError(
            f"El motivo '{valor}' no está permitido por {CAT_14}.",
            details={
                "codigo": "REPORT_REASON_INVALID",
                "campo": "motivo",
                "politica": CAT_14,
                "motivosPermitidos": list(MOTIVOS_PERMITIDOS),
            },
        )
    return texto


def normalizar_tipo_contenido(valor: object, contenido_id: str) -> str:
    """Deduce el tipo cuando el cliente no lo envía explícitamente."""

    texto = _clave(valor)
    alias = {"reseña": TIPO_RESENA, "review": TIPO_RESENA, "resena": TIPO_RESENA}
    texto = alias.get(texto, texto)
    if texto in TIPOS_CONTENIDO:
        return texto
    if contenido_id.startswith(("prod_", "producto")):
        return TIPO_PRODUCTO
    if contenido_id.startswith(("res_", "resena_", "resena", "review")):
        return TIPO_RESENA
    if contenido_id.startswith("usr_"):
        return TIPO_USUARIO
    if texto:
        raise InvalidReportError(
            f"El tipo de contenido '{valor}' no es válido.",
            details={
                "codigo": "REPORT_CONTENT_TYPE_INVALID",
                "campo": "tipoContenido",
                "permitidos": list(TIPOS_CONTENIDO),
            },
        )
    return TIPO_PRODUCTO


def validar_contenido_id(valor: object) -> str:
    contenido_id = str(valor or "").strip()
    if not contenido_id:
        raise InvalidReportError(
            "El contenido a reportar es obligatorio.",
            details={"codigo": "REPORT_CONTENT_REQUIRED", "campo": "contenidoId"},
        )
    return contenido_id


def tiene_evidencia(valor: Any) -> bool:
    """Una evidencia válida es texto, un objeto con datos o una lista no vacía."""

    if isinstance(valor, str):
        return bool(valor.strip())
    if isinstance(valor, Mapping):
        return any(tiene_evidencia(item) for item in valor.values())
    if isinstance(valor, (list, tuple, set)):
        return any(tiene_evidencia(item) for item in valor)
    return valor is not None and bool(str(valor).strip())


def validar_evidencia(valor: Any) -> Any:
    if not tiene_evidencia(valor):
        raise InvalidReportError(
            "La evidencia del reporte es obligatoria.",
            details={
                "codigo": "REPORT_EVIDENCE_REQUIRED",
                "campo": "evidencia",
                "politica": CAT_14,
            },
        )
    return valor


def evidencia_hash(valor: Any) -> str:
    """Huella inmutable de la evidencia; el contenido queda en almacenamiento restringido."""

    serializado = json.dumps(valor, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def normalizar_decision(valor: object) -> str:
    texto = _clave(valor)
    alias = {
        "desestimar": DECISION_DESIMISION,
        "desestimado": DECISION_DESIMISION,
        "desestimada": DECISION_DESIMISION,
        "rechazar": DECISION_DESIMISION,
        "sin_accion": DECISION_DESIMISION,
        "sin_sancion": DECISION_DESIMISION,
        "sancionar": DECISION_SANCION,
        "sancion": DECISION_SANCION,
        "sancionado": DECISION_SANCION,
        "aplicar_sancion": DECISION_SANCION,
        "sancionar_usuario": DECISION_SANCION,
    }
    decision = alias.get(texto, texto)
    if decision not in DECISIONES:
        raise InvalidReportError(
            f"La decisión '{valor}' no es válida.",
            details={
                "codigo": "REPORT_DECISION_INVALID",
                "campo": "decision",
                "permitidas": list(DECISIONES),
            },
        )
    return decision


def normalizar_tipo_sancion(valor: object) -> str:
    texto = _clave(valor)
    sancion = _ALIAS_TIPOS_SANCION.get(texto, texto)
    if sancion not in TIPOS_SANCION:
        raise InvalidSanctionError(
            f"El tipo de sanción '{valor}' no está permitido por {CAT_15}.",
            details={
                "codigo": "SANCTION_TYPE_INVALID",
                "campo": "tipo",
                "politica": CAT_15,
                "permitidos": list(TIPOS_SANCION),
            },
        )
    return sancion


def normalizar_duracion(valor: object, *, por_defecto: int) -> int:
    """CAT-16 fija la duración por defecto de una suspensión temporal."""

    if valor is None or (isinstance(valor, str) and not valor.strip()):
        duracion = int(por_defecto)
    else:
        if isinstance(valor, bool) or not str(valor).strip().lstrip("+").isdigit():
            raise InvalidSanctionError(
                "La duración de la sanción debe ser un entero positivo.",
                details={"codigo": "SANCTION_DURATION_INVALID", "campo": "duracionDias"},
            )
        duracion = int(valor)
    if duracion <= 0 or duracion > 365:
        raise InvalidSanctionError(
            "La duración de la sanción debe estar entre 1 y 365 días.",
            details={
                "codigo": "SANCTION_DURATION_INVALID",
                "campo": "duracionDias",
                "minimo": 1,
                "maximo": 365,
                "politica": CAT_16,
            },
        )
    return duracion


def normalizar_accion_contenido(valor: object, *, tipo_sancion: str) -> str:
    texto = _clave(valor)
    if texto in ACCIONES_CONTENIDO:
        return texto
    # Las medidas que retiran al usuario de la plataforma archivan el contenido;
    # una advertencia solo lo restringe temporalmente.
    return ACCION_RESTRINGIR if tipo_sancion == TIPO_ADVERTENCIA else ACCION_ARCHIVAR


def observacion_o_default(valor: object, *, decision: str) -> str:
    texto = str(valor or "").strip()
    if texto:
        return texto
    return (
        "El reporte fue desestimado por falta de evidencia suficiente."
        if decision == DECISION_DESIMISION
        else "Se aplicó una sanción conforme a las políticas de la comunidad."
    )


@dataclass
class Resolucion:
    """Resultado de la gestión del reporte (FUN-36)."""

    decision: str
    observacion: str
    fecha: datetime
    administrador_id: str = ""
    sancion_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "sancion": self.sancion_id,
            "observacion": self.observacion,
            "fecha": self.fecha.isoformat(),
            "administradorId": self.administrador_id,
        }

    @classmethod
    def from_dict(cls, valor: Mapping[str, Any] | None) -> Resolucion | None:
        if not valor:
            return None
        fecha = valor.get("fecha")
        return cls(
            decision=str(valor.get("decision", "")),
            observacion=str(valor.get("observacion", "")),
            fecha=fecha if isinstance(fecha, datetime) else datetime.fromisoformat(str(fecha)),
            administrador_id=str(valor.get("administradorId", "")),
            sancion_id=valor.get("sancion") if isinstance(valor.get("sancion"), str) else None,
        )


@dataclass
class Reporte:
    """Reporte persistido; ``reportante_id`` nunca se expone en la API."""

    id: str
    contenido_id: str
    motivo: str
    evidencia: Any
    reportante_id: str
    fecha: datetime
    tipo_contenido: str = TIPO_PRODUCTO
    estado: str = ESTADO_ABIERTO
    evidencia_hash: str = ""
    resolucion: Resolucion | None = None
    metadatos: dict[str, Any] = field(default_factory=dict)


@dataclass
class Sancion:
    """Medida disciplinaria de CAT-15, apelable por el canal definido."""

    id: str
    contenido_id: str
    tipo: str
    duracion_dias: int
    usuario_afectado: str
    fecha: datetime
    reporte_id: str | None = None
    motivo: str = ""
    observacion: str = ""
    evidencia: Any = None
    evidencia_hash: str = ""
    accion_contenido: str = ACCION_ARCHIVAR
    apelable: bool = True
    notificado: bool = False
    estado_contenido: str | None = None
