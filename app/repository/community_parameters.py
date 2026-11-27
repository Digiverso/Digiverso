"""Persistencia versionada e inmutable de los parámetros de comunidad (HU-21)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.domain.community_parameters import CommunityParameterVersion
from app.repository.database import Database

_COMMUNITY_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS community_parameter_versions (
    version        INTEGER PRIMARY KEY,
    vigente_desde  TEXT NOT NULL,
    modulo         TEXT NOT NULL,
    actor_id       TEXT NOT NULL,
    actor_roles    TEXT NOT NULL,
    motivo         TEXT NOT NULL DEFAULT '',
    anteriores     TEXT NOT NULL DEFAULT '{}',
    valores        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_community_parameter_versions_modulo
    ON community_parameter_versions(modulo, version DESC);
"""


def _parse_datetime(raw: str) -> datetime:
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class SQLiteCommunityParameterRepository:
    """Solo inserta versiones; nunca actualiza ni borra filas."""

    def __init__(self, database: Database) -> None:
        self.database = database
        # Tabla propia: no se amplía el esquema compartido con otras HU.
        with self.database.connection() as connection:
            connection.executescript(_COMMUNITY_VERSION_TABLE)

    @staticmethod
    def _to_domain(row: Any) -> CommunityParameterVersion:
        return CommunityParameterVersion(
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
        valores: dict[str, Any],
        anteriores: dict[str, Any],
        actor_id: str,
        actor_roles: tuple[str, ...],
        motivo: str,
        vigente_desde: datetime,
        modulo: str,
    ) -> CommunityParameterVersion:
        """Inserta una versión nueva calculando su número dentro de la transacción."""

        fecha = vigente_desde.astimezone(timezone.utc).isoformat()
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS siguiente "
                "FROM community_parameter_versions"
            ).fetchone()
            version = int(row["siguiente"])
            connection.execute(
                """
                INSERT INTO community_parameter_versions
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
        return CommunityParameterVersion(
            version=version,
            vigente_desde=vigente_desde.astimezone(timezone.utc),
            modulo=modulo,
            valores=dict(valores),
            anteriores=dict(anteriores),
            actor_id=actor_id,
            actor_roles=tuple(actor_roles),
            motivo=motivo,
        )

    def latest(self) -> CommunityParameterVersion | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM community_parameter_versions ORDER BY version DESC LIMIT 1"
            ).fetchone()
        return self._to_domain(row) if row is not None else None

    def get(self, version: int) -> CommunityParameterVersion | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM community_parameter_versions WHERE version = ?", (version,)
            ).fetchone()
        return self._to_domain(row) if row is not None else None

    def list_versions(self, *, limit: int = 50) -> list[CommunityParameterVersion]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM community_parameter_versions ORDER BY version DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._to_domain(row) for row in rows]
