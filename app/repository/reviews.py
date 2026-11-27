"""Repositorio SQLite de reseñas y agregación de calificaciones (HU-18)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.domain.reviews import Review
from app.repository.database import Database


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _review(row: sqlite3.Row) -> Review:
    return Review(
        id=row["id"],
        product_id=row["producto_id"],
        user_id=row["usuario_id"],
        calificacion=int(row["calificacion"]),
        texto=row["texto"],
        fecha=_datetime(row["fecha"]),
        visible=bool(row["visible"]),
    )


class SQLiteReviewRepository:
    """Persistencia de reseñas con índice por producto, usuario y visibilidad."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, review: Review) -> Review:
        with self.database.connection() as connection:
            if review.id:
                review_id = review.id
            else:
                row = connection.execute(
                    """
                    SELECT COALESCE(MAX(CAST(substr(id, 5) AS INTEGER)), 0) + 1 AS next_number
                    FROM reviews WHERE id GLOB 'rev_[0-9]*'
                    """
                ).fetchone()
                review_id = f"rev_{int(row['next_number']):03d}"
            connection.execute(
                """
                INSERT INTO reviews
                    (id, producto_id, usuario_id, calificacion, texto, fecha, visible)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    review.product_id,
                    review.user_id,
                    review.calificacion,
                    review.texto,
                    _iso(review.fecha),
                    int(review.visible),
                ),
            )
        return Review(
            id=review_id,
            product_id=review.product_id,
            user_id=review.user_id,
            calificacion=review.calificacion,
            texto=review.texto,
            fecha=review.fecha,
            visible=review.visible,
        )

    def exists_for(self, product_id: str, user_id: str) -> bool:
        """COMU-03: comprueba cualquier reseña previa, visible o no."""

        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM reviews WHERE producto_id = ? AND usuario_id = ? LIMIT 1",
                (product_id, user_id),
            ).fetchone()
        return row is not None

    def hide(self, review_id: str) -> None:
        """Retiro lógico para Control de publicaciones (sin borrar la reseña)."""

        with self.database.connection() as connection:
            connection.execute(
                "UPDATE reviews SET visible = 0 WHERE id = ?", (review_id,)
            )

    def list_visible(
        self, product_id: str, *, page: int = 1, page_size: int = 20
    ) -> tuple[list[Review], int]:
        """Reseñas visibles ordenadas por fecha descendente, con total."""

        offset = (page - 1) * page_size
        with self.database.connection() as connection:
            total = int(
                connection.execute(
                    "SELECT COUNT(*) AS total FROM reviews "
                    "WHERE producto_id = ? AND visible = 1",
                    (product_id,),
                ).fetchone()["total"]
            )
            rows = connection.execute(
                """
                SELECT id, producto_id, usuario_id, calificacion, texto, fecha, visible
                FROM reviews
                WHERE producto_id = ? AND visible = 1
                ORDER BY fecha DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (product_id, page_size, offset),
            ).fetchall()
        return [_review(row) for row in rows], total

    def aggregate(self, product_id: str) -> dict[int, int]:
        """Agregación SQL de calificaciones visibles por producto."""

        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT calificacion, COUNT(*) AS total
                FROM reviews
                WHERE producto_id = ? AND visible = 1
                GROUP BY calificacion
                ORDER BY calificacion
                """,
                (product_id,),
            ).fetchall()
        return {int(row["calificacion"]): int(row["total"]) for row in rows}
