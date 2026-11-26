"""Reglas puras del control de publicaciones (HU-11, SUB-13).

Las decisiones de revisión no se validan en el esquema HTTP: el checklist, el
motivo CAT-14 y la observación se normalizan aquí para que el mismo contrato
sea reutilizable por la API, pruebas y otros casos de uso.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from app.domain.exceptions import InvalidPublicationReviewError

EVENTO_PRODUCT_REVIEWED = "product.reviewed"
CAT_14 = "CAT-14"

DECISION_APROBADA = "aprobado"
DECISION_RECHAZADA = "rechazado"

# FUN-33: todas las casillas deben estar marcadas para poder aprobar.
CHECKLIST_ITEMS: tuple[str, ...] = (
    "autoria",
    "edad",
    "derechos",
    "contenido",
    "funciones",
)

# Se aceptan alias habituales del checklist sin debilitar la regla: siguen
# siendo las cinco verificaciones las que deben quedar completas.
_CHECKLIST_ALIASES: dict[str, str] = {
    "autoria": "autoria",
    "autoria_propia": "autoria",
    "autor": "autoria",
    "edad": "edad",
    "edad_adecuada": "edad",
    "edad_adecuada_para_el_contenido": "edad",
    "derechos": "derechos",
    "derechos_de_autor": "derechos",
    "derechos_de_autoría": "derechos",
    "copyright": "derechos",
    "contenido": "contenido",
    "contenido_seguro": "contenido",
    "seguridad": "contenido",
    "funciones": "funciones",
    "funcionamiento": "funciones",
    "funciones_verificadas": "funciones",
    "authorship": "autoria",
    "age": "edad",
    "rights": "derechos",
    "content": "contenido",
    "functions": "funciones",
}

# CAT-14: códigos sugeridos de rechazo. La regla exige motivo no vacío y
# observación; no se impone una lista cerrada porque la HU no la define.
MOTIVOS_RECHAZO: tuple[str, ...] = (
    "autoria_no_verificada",
    "edad_inadecuada",
    "derechos_no_aclarados",
    "contenido_inseguro",
    "funciones_no_verificadas",
    "cat-14",
    "otro",
)


@dataclass(frozen=True)
class PoliticaAplicable:
    codigo: str
    descripcion: str


POLITICAS_PUBLICACION: tuple[PoliticaAplicable, ...] = (
    PoliticaAplicable("CAT-01", "Precio entero no negativo en COP."),
    PoliticaAplicable("CAT-03", "Rango de edad apto para el contenido."),
    PoliticaAplicable("CAT-09", "Imágenes mínimas declaradas por el productor."),
    PoliticaAplicable("CAT-11", "Nombre del producto válido."),
    PoliticaAplicable("CAT-12", "Descripción del producto válida."),
    PoliticaAplicable("CAT-13", "Categorías existentes y activas."),
    PoliticaAplicable(CAT_14, "Motivo de rechazo documentado con observación."),
)


def _clave_checklist(valor: object) -> str:
    return str(valor).strip().lower().replace(" ", "_")


def normalizar_checklist(valor: object) -> dict[str, bool]:
    """Devuelve las cinco verificaciones en ``True`` o falla con 400.

    Acepta un objeto ``{checklistItem: bool}`` o una lista de elementos
    marcados. Las claves desconocidas se ignoran; lo que no se puede omitir es
    ninguna de las cinco verificaciones obligatorias.
    """

    if isinstance(valor, Mapping):
        declarados: dict[str, bool] = {}
        for clave, marcado in valor.items():
            canonico = _CHECKLIST_ALIASES.get(_clave_checklist(clave))
            if canonico is not None:
                declarados[canonico] = bool(marcado)
    elif isinstance(valor, (list, tuple, set, frozenset)):
        declarados = {}
        for clave in valor:
            canonico = _CHECKLIST_ALIASES.get(_clave_checklist(clave))
            if canonico is not None:
                declarados[canonico] = True
    else:
        raise InvalidPublicationReviewError(
            f"El checklist de revisión es obligatorio y debe estar completo ({', '.join(CHECKLIST_ITEMS)}).",
            details={"razon": "checklist_incompleto", "requeridos": list(CHECKLIST_ITEMS)},
        )

    faltantes = [item for item in CHECKLIST_ITEMS if declarados.get(item) is not True]
    if faltantes:
        raise InvalidPublicationReviewError(
            "El checklist de revisión está incompleto.",
            details={
                "razon": "checklist_incompleto",
                "faltantes": faltantes,
                "requeridos": list(CHECKLIST_ITEMS),
            },
        )
    return {item: True for item in CHECKLIST_ITEMS}


def normalizar_motivo(valor: object) -> str:
    """Valida el motivo CAT-14: debe existir y no estar vacío."""

    motivo = str(valor or "").strip()
    if not motivo:
        raise InvalidPublicationReviewError(
            f"El rechazo requiere un motivo ({CAT_14}) y una observación.",
            details={
                "razon": "motivo_cat_14_requerido",
                "motivosSugeridos": list(MOTIVOS_RECHAZO),
            },
        )
    return motivo[:200]


def validar_observacion(valor: object) -> str:
    observacion = str(valor or "").strip()
    if not observacion:
        raise InvalidPublicationReviewError(
            f"El rechazo requiere una observación que justifique el motivo {CAT_14}.",
            details={"razon": "observacion_requerida"},
        )
    return observacion[:1000]


@dataclass(frozen=True)
class ProductReviewedEvent:
    """Evento de dominio ``product.reviewed`` publicado tras el commit."""

    producto_id: str
    decision: str
    administrador_id: str
    fecha: datetime
    checklist: dict[str, bool] | None = None
    motivo: str | None = None
    observacion: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "productoId": self.producto_id,
            "decision": self.decision,
            "administradorId": self.administrador_id,
            "fecha": self.fecha.astimezone().isoformat(),
            "checklist": dict(self.checklist or {}),
            "motivo": self.motivo,
            "observacion": self.observacion,
        }
