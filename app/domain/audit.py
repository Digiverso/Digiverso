"""Evento de auditoría para cambios en categorías."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class AuditEvent:
    entidad: str
    entidad_id: str
    accion: str
    actor_id: str
    actor_roles: tuple[str, ...]
    fecha: datetime
    cambios: dict[str, Any]
