"""Persistencia versionada e inmutable de los parámetros de autenticación."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.domain.auth_parameters import AuthParameterVersion
from app.repository.database import Database


def _parse_datetime(raw: str) -> datetime:
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class SQLiteAuthParameterRepository:
    """Solo permite insertar versiones; nunca actualiza ni borra filas."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _to_domain(row: Any) -> AuthParameterVersion:
        return AuthParameterVersion(
            version=int(row["version"]),
            vigente_desde=_parse_datetime(row["vigente_desde"]),
            modulo=row["modulo"],
            valores=dict(json.loads(row["valores"])),
            anteriores=dict(json.loads(row["anteriores"])),
            actor_id=row["actor_id"],
            actor_roles=tuple(json.loads(row["actor_roles"])),
            motivo=row["motivo"],
        )

    def save(
        self,
        *,
        valores: dict[str, int],
        anteriores: dict[str, int],
        actor_id: str,
        actor_roles: tuple[str, ...],
        motivo: str,
        vigente_desde: datetime,
        modulo: str,
    ) -> AuthParameterVersion:
        """Inserta una versión nueva calculando su número dentro de la transacción."""

        fecha = vigente_desde.astimezone(timezone.utc).isoformat()
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS siguiente "
                "FROM auth_parameter_versions"
            ).fetchone()
            version = int(row["siguiente"])
            connection.execute(
                """
                INSERT INTO auth_parameter_versions
                    (version, vigente_desde, modulo, actor_id, actor_roles,
                     motivo, anteriores, valores)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version,
                    fecha,
                    modulo,
                    actor_id,
                    json.dumps(list(actor_roles), ensure_ascii=False),
                    motivo,
                    json.dumps(anteriores, ensure_ascii=False, sort_keys=True),
                    json.dumps(valores, ensure_ascii=False, sort_keys=True),
                ),
            )
        return AuthParameterVersion(
            version=version,
            vigente_desde=vigente_desde.astimezone(timezone.utc),
            modulo=modulo,
            valores=dict(valores),
            anteriores=dict(anteriores),
            actor_id=actor_id,
            actor_roles=tuple(actor_roles),
            motivo=motivo,
        )

    def latest(self) -> AuthParameterVersion | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM auth_parameter_versions ORDER BY version DESC LIMIT 1"
            ).fetchone()
        return self._to_domain(row) if row is not None else None

    def get(self, version: int) -> AuthParameterVersion | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM auth_parameter_versions WHERE version = ?", (version,)
            ).fetchone()
        return self._to_domain(row) if row is not None else None

    def list_versions(self, *, limit: int = 50) -> list[AuthParameterVersion]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM auth_parameter_versions ORDER BY version DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._to_domain(row) for row in rows]
