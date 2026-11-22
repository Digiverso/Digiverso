"""Repositorio de categorías: materialized path y borrado lógico."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Iterable

from app.domain.category import ESTADO_ACTIVA, ESTADO_INACTIVA, Category
from app.domain.exceptions import DuplicateCategoryNameError
from app.repository.database import Database


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


class SQLiteCategoryRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    # ---------------------------------------------------------------- lectura
    def _rows_to_categories(self, rows: Iterable[sqlite3.Row]) -> list[Category]:
        return [
            Category(
                id=row["id"],
                nombre=row["nombre"],
                padre_id=row["padre_id"],
                estado=row["estado"],
                orden=row["orden"],
                descripcion=row["descripcion"],
                ruta=row["ruta"],
                creado_en=_from_iso(row["creado_en"]),
                actualizado_en=_from_iso(row["actualizado_en"]),
                eliminado_en=(
                    _from_iso(row["eliminado_en"]) if row["eliminado_en"] else None
                ),
            )
            for row in rows
        ]

    def get(self, category_id: str) -> Category | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM categories WHERE id = ?", (category_id,)
            ).fetchone()
        return self._rows_to_categories([row])[0] if row else None

    def list_all(self) -> list[Category]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT * FROM categories").fetchall()
        return self._rows_to_categories(rows)

    def list_active(self) -> list[Category]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM categories WHERE estado = ?", (ESTADO_ACTIVA,)
            ).fetchall()
        return self._rows_to_categories(rows)

    def exists_by_name(
        self, normalized_name: str, parent_id: str | None, *, exclude_id: str | None = None
    ) -> bool:
        sql = """
            SELECT 1 FROM categories
            WHERE nombre_normalizado = ? AND COALESCE(padre_id, '') = COALESCE(?, '')
        """
        params: list[object] = [normalized_name, parent_id]
        if exclude_id is not None:
            sql += " AND id <> ?"
            params.append(exclude_id)
        with self.database.connection() as connection:
            return connection.execute(sql, params).fetchone() is not None

    def count_active_products_in_subtree(self, path: str) -> int:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM productos AS p
                JOIN categories AS c ON c.id = p.categoria_id
                WHERE p.activo = 1 AND substr(c.ruta, 1, ?) = ?
                """,
                (len(path), path),
            ).fetchone()
        return int(row["total"])

    def next_id(self) -> str:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(CAST(substr(id, 5) AS INTEGER)), 0) + 1 AS next_number
                FROM categories
                WHERE id GLOB 'cat_[0-9]*'
                """
            ).fetchone()
        return f"cat_{int(row['next_number']):03d}"

    # ---------------------------------------------------------------- escritura
    def save(self, category: Category) -> Category:
        now = datetime.now(timezone.utc)
        category.creado_en = now
        category.actualizado_en = now
        try:
            with self.database.connection() as connection:
                connection.execute(
                    """
                    INSERT INTO categories (
                        id, nombre, nombre_normalizado, descripcion, padre_id,
                        estado, orden, ruta, creado_en, actualizado_en, eliminado_en
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        category.id,
                        category.nombre,
                        category.nombre_normalizado,
                        category.descripcion,
                        category.padre_id,
                        category.estado,
                        category.orden,
                        category.ruta,
                        _iso(category.creado_en),
                        _iso(category.actualizado_en),
                        None,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateCategoryNameError(
                "Ya existe una categoría con ese nombre bajo el mismo padre.",
                details={"padreId": category.padre_id, "nombre": category.nombre},
            ) from error
        return category

    def update(self, category: Category, *, previous_path: str) -> Category:
        """Actualiza la categoría y reescribe la ruta de todo su subárbol."""

        category.actualizado_en = datetime.now(timezone.utc)
        new_path = category.ruta
        try:
            with self.database.connection() as connection:
                if previous_path != new_path:
                    connection.execute(
                        """
                        UPDATE categories
                        SET ruta = ? || substr(ruta, ?)
                        WHERE substr(ruta, 1, ?) = ? AND id <> ?
                        """,
                        (
                            new_path,
                            len(previous_path) + 1,
                            len(previous_path),
                            previous_path,
                            category.id,
                        ),
                    )
                connection.execute(
                    """
                    UPDATE categories
                    SET nombre = ?, nombre_normalizado = ?, descripcion = ?,
                        padre_id = ?, estado = ?, orden = ?, ruta = ?, actualizado_en = ?
                    WHERE id = ?
                    """,
                    (
                        category.nombre,
                        category.nombre_normalizado,
                        category.descripcion,
                        category.padre_id,
                        category.estado,
                        category.orden,
                        new_path,
                        _iso(category.actualizado_en),
                        category.id,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateCategoryNameError(
                "Ya existe una categoría con ese nombre bajo el mismo padre.",
                details={"padreId": category.padre_id, "nombre": category.nombre},
            ) from error
        return category

    def deactivate(self, category: Category) -> Category:
        now = datetime.now(timezone.utc)
        category.estado = ESTADO_INACTIVA
        category.eliminado_en = now
        category.actualizado_en = now
        with self.database.connection() as connection:
            connection.execute(
                """
                UPDATE categories
                SET estado = ?, eliminado_en = ?, actualizado_en = ?
                WHERE id = ?
                """,
                (
                    ESTADO_INACTIVA,
                    _iso(now),
                    _iso(now),
                    category.id,
                ),
            )
        return category

    def add_product(
        self, product_id: str, category_id: str, *, activo: bool = True
    ) -> None:
        """Registro mínimo de producto para validar la regla FUN-19."""

        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO productos (id, categoria_id, estado, activo)
                VALUES (?, ?, 'publicado', ?)
                """,
                (product_id, category_id, int(activo)),
            )
