"""Persistencia del registro de auditoría de cambios de categorías."""

from __future__ import annotations

import json
from datetime import timezone
from typing import Any

from app.domain.audit import AuditEvent
from app.repository.database import Database


def _iso(event: AuditEvent) -> str:
    return event.fecha.astimezone(timezone.utc).isoformat()


class SQLiteAuditRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def record(self, event: AuditEvent) -> None:
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO audit_log
                    (entidad, entidad_id, accion, actor_id, actor_roles, fecha, cambios)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.entidad,
                    event.entidad_id,
                    event.accion,
                    event.actor_id,
                    json.dumps(list(event.actor_roles), ensure_ascii=False),
                    _iso(event),
                    json.dumps(event.cambios, ensure_ascii=False, default=str),
                ),
            )

    def list_for_entity(self, entity_id: str) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT accion, actor_id, actor_roles, fecha, cambios
                FROM audit_log
                WHERE entidad = 'categoria' AND entidad_id = ?
                ORDER BY id
                """,
                (entity_id,),
            ).fetchall()
        return [
            {
                "accion": row["accion"],
                "actorId": row["actor_id"],
                "actorRoles": json.loads(row["actor_roles"]),
                "fecha": row["fecha"],
                "cambios": json.loads(row["cambios"]),
            }
            for row in rows
        ]
