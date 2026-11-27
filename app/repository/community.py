"""Persistencia SQLite de seguidos, intereses y contadores (HU-19).

Las tablas se crean aquí, de forma idempotente, para no modificar el esquema
compartido de ``app/repository/database.py`` usado por otras historias.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.repository.database import Database

COMMUNITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS community_follows (
    seguidor_id TEXT NOT NULL,
    seguido_id  TEXT NOT NULL,
    creado_en   TEXT NOT NULL,
    PRIMARY KEY (seguidor_id, seguido_id)
);

CREATE INDEX IF NOT EXISTS idx_community_follows_seguido
    ON community_follows(seguido_id);

CREATE TABLE IF NOT EXISTS community_interests (
    usuario_id  TEXT NOT NULL,
    categoria_id TEXT NOT NULL,
    PRIMARY KEY (usuario_id, categoria_id)
);

CREATE TABLE IF NOT EXISTS community_stats (
    usuario_id     TEXT PRIMARY KEY,
    seguidores     INTEGER NOT NULL DEFAULT 0,
    siguiendo      INTEGER NOT NULL DEFAULT 0,
    actualizado_en TEXT NOT NULL
);
"""


class SQLiteCommunityRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        with self.database.connection() as connection:
            connection.executescript(COMMUNITY_SCHEMA)

    # ------------------------------------------------------------- seguidos
    def is_following(self, seguidor_id: str, seguido_id: str) -> bool:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM community_follows WHERE seguidor_id = ? AND seguido_id = ?",
                (seguidor_id, seguido_id),
            ).fetchone()
        return row is not None

    def follow(self, seguidor_id: str, seguido_id: str, creado_en: datetime) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO community_follows (seguidor_id, seguido_id, creado_en) "
                "VALUES (?, ?, ?)",
                (seguidor_id, seguido_id, creado_en.isoformat()),
            )

    def unfollow(self, seguidor_id: str, seguido_id: str) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute(
                "DELETE FROM community_follows WHERE seguidor_id = ? AND seguido_id = ?",
                (seguidor_id, seguido_id),
            )
        return cursor.rowcount > 0

    def followed_ids(self, seguidor_id: str) -> list[str]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT seguido_id FROM community_follows WHERE seguidor_id = ? "
                "ORDER BY creado_en, seguido_id",
                (seguidor_id,),
            ).fetchall()
        return [str(row["seguido_id"]) for row in rows]

    def count_following(self, usuario_id: str) -> int:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM community_follows WHERE seguidor_id = ?",
                (usuario_id,),
            ).fetchone()
        return int(row["total"])

    def count_followers(self, usuario_id: str) -> int:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM community_follows WHERE seguido_id = ?",
                (usuario_id,),
            ).fetchone()
        return int(row["total"])

    def recompute_stats(
        self, usuario_id: str, actualizado_en: datetime
    ) -> dict[str, Any]:
        """Recalcula contadores derivados de la tabla de relaciones."""

        seguidores = self.count_followers(usuario_id)
        siguiendo = self.count_following(usuario_id)
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO community_stats
                    (usuario_id, seguidores, siguiendo, actualizado_en)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(usuario_id) DO UPDATE SET
                    seguidores = excluded.seguidores,
                    siguiendo = excluded.siguiendo,
                    actualizado_en = excluded.actualizado_en
                """,
                (usuario_id, seguidores, siguiendo, actualizado_en.isoformat()),
            )
        return {
            "seguidores": seguidores,
            "siguiendo": siguiendo,
            "actualizado_en": actualizado_en.isoformat(),
        }

    def stats(self, usuario_id: str) -> dict[str, Any]:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT seguidores, siguiendo FROM community_stats WHERE usuario_id = ?",
                (usuario_id,),
            ).fetchone()
        if row is None:
            return {"seguidores": 0, "siguiendo": 0}
        return {"seguidores": int(row["seguidores"]), "siguiendo": int(row["siguiendo"])}

    # ------------------------------------------------------------- intereses
    def replace_interests(self, usuario_id: str, categorias: list[str]) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "DELETE FROM community_interests WHERE usuario_id = ?", (usuario_id,)
            )
            connection.executemany(
                "INSERT INTO community_interests (usuario_id, categoria_id) VALUES (?, ?)",
                [(usuario_id, categoria) for categoria in categorias],
            )

    def interests(self, usuario_id: str) -> list[str]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT categoria_id FROM community_interests WHERE usuario_id = ? "
                "ORDER BY categoria_id",
                (usuario_id,),
            ).fetchall()
        return [str(row["categoria_id"]) for row in rows]

    def purchased_ids(self, usuario_id: str) -> list[str]:
        """Productos con licencia vigente del usuario (exclusión de comprados)."""

        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT DISTINCT producto_id FROM licencias "
                "WHERE actor_id = ? AND vigente = 1 ORDER BY producto_id",
                (usuario_id,),
            ).fetchall()
        return [str(row["producto_id"]) for row in rows]
