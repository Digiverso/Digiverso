"""Repositorio SQLite de productos y sus licencias (HU-08)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Iterable

from app.domain.product import ESTADO_PUBLICADO, Medio, Product
from app.repository.database import Database


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _medios_from_json(raw: str | None) -> list[Medio]:
    try:
        items = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [
        Medio(
            id=str(item.get("id")) if item.get("id") else None,
            tipo=str(item.get("tipo", "imagen")),
            url=str(item.get("url", "")),
            orden=int(item.get("orden", 0) or 0),
        )
        for item in items
        if isinstance(item, dict)
    ]


class SQLiteProductRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    # ---------------------------------------------------------------- lectura
    def _rows_to_products(self, rows: Iterable[sqlite3.Row]) -> list[Product]:
        products: list[Product] = []
        for row in rows:
            creado_en = _datetime(row["creado_en"]) or datetime.now(timezone.utc)
            actualizado_en = _datetime(row["actualizado_en"]) or creado_en
            estado_desde = _datetime(row["estado_desde"]) or creado_en
            try:
                categorias = json.loads(row["categorias"] or "[]")
            except (TypeError, ValueError):
                categorias = []
            products.append(
                Product(
                    id=row["id"],
                    nombre=row["nombre"] or "",
                    descripcion=row["descripcion"] or "",
                    precio=int(row["precio"] or 0),
                    autor_id=row["autor_id"] or "",
                    categoria_id=row["categoria_id"],
                    moneda=row["moneda"] or "COP",
                    edad_minima=int(row["edad_minima"] or 0),
                    edad_maxima=int(row["edad_maxima"] or 99),
                    categorias=[str(item) for item in categorias],
                    medios=_medios_from_json(row["medios"]),
                    estado=row["estado"],
                    activo=bool(row["activo"]),
                    creado_en=creado_en,
                    actualizado_en=actualizado_en,
                    estado_desde=estado_desde,
                    archivado_en=_datetime(row["archivado_en"]),
                    archivo_hash=row["archivo_hash"],
                    cambios_pendientes=bool(row["cambios_pendientes"]),
                )
            )
        return products

    def get(self, product_id: str) -> Product | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM productos WHERE id = ?", (product_id,)
            ).fetchone()
        return self._rows_to_products([row])[0] if row else None

    def list_by_estado(self, estado: str) -> list[Product]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM productos WHERE estado = ? ORDER BY creado_en DESC, id DESC",
                (estado,),
            ).fetchall()
        return self._rows_to_products(rows)

    def list_showcase(self) -> list[Product]:
        """Vitrina: únicamente productos publicados y activos."""

        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM productos
                WHERE estado = ? AND activo = 1
                ORDER BY creado_en DESC, id DESC
                """,
                (ESTADO_PUBLICADO,),
            ).fetchall()
        return self._rows_to_products(rows)

    def next_id(self) -> str:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(CAST(substr(id, 6) AS INTEGER)), 0) + 1 AS next_number
                FROM productos
                WHERE id GLOB 'prod_[0-9]*'
                """
            ).fetchone()
        return f"prod_{int(row['next_number']):03d}"

    # ---------------------------------------------------------------- escritura
    def _values(self, product: Product) -> tuple[Any, ...]:
        """Valores en el orden de la sentencia UPDATE (sin el ``id``)."""

        return (
            product.categoria_id or (product.categorias[0] if product.categorias else ""),
            product.estado,
            int(product.activo),
            product.nombre,
            product.descripcion,
            product.precio,
            product.moneda,
            product.edad_minima,
            product.edad_maxima,
            json.dumps(product.categorias, ensure_ascii=False),
            json.dumps([asdict(medio) for medio in product.medios], ensure_ascii=False),
            product.autor_id,
            _iso(product.creado_en),
            _iso(product.actualizado_en),
            _iso(product.estado_desde),
            _iso(product.archivado_en) if product.archivado_en else None,
            product.archivo_hash,
            int(product.cambios_pendientes),
        )

    def save(self, product: Product) -> Product:
        columns = (
            "id, categoria_id, estado, activo, nombre, descripcion, precio, moneda, "
            "edad_minima, edad_maxima, categorias, medios, autor_id, creado_en, "
            "actualizado_en, estado_desde, archivado_en, archivo_hash, cambios_pendientes"
        )
        placeholders = ", ".join("?" for _ in columns.split(", "))
        with self.database.connection() as connection:
            connection.execute(
                f"INSERT INTO productos ({columns}) VALUES ({placeholders})",
                (product.id, *self._values(product)),
            )
        return product

    def update(self, product: Product) -> Product:
        with self.database.connection() as connection:
            connection.execute(
                """
                UPDATE productos SET
                    categoria_id = ?, estado = ?, activo = ?, nombre = ?, descripcion = ?,
                    precio = ?, moneda = ?, edad_minima = ?, edad_maxima = ?,
                    categorias = ?, medios = ?, autor_id = ?, creado_en = ?,
                    actualizado_en = ?, estado_desde = ?, archivado_en = ?,
                    archivo_hash = ?, cambios_pendientes = ?
                WHERE id = ?
                """,
                (*self._values(product), product.id),
            )
        return product

    # --------------------------------------------------------------- licencias
    def add_license(
        self, product_id: str, *, tipo: str = "estandar", license_id: str | None = None
    ) -> dict[str, Any]:
        """Registro mínimo de licencia para verificar la regla FUN-24."""

        with self.database.connection() as connection:
            if license_id is None:
                row = connection.execute(
                    """
                    SELECT COALESCE(MAX(CAST(substr(id, 5) AS INTEGER)), 0) + 1 AS next_number
                    FROM licencias WHERE id GLOB 'lic_[0-9]*'
                    """
                ).fetchone()
                license_id = f"lic_{int(row['next_number']):03d}"
            connection.execute(
                """
                INSERT INTO licencias (id, producto_id, tipo, vigente, creado_en)
                VALUES (?, ?, ?, 1, ?)
                """,
                (license_id, product_id, tipo, _iso(datetime.now(timezone.utc))),
            )
        return {"id": license_id, "productoId": product_id, "tipo": tipo, "vigente": True}

    def list_licenses(self, product_id: str) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT id, producto_id, tipo, vigente, creado_en FROM licencias "
                "WHERE producto_id = ? ORDER BY id",
                (product_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "productoId": row["producto_id"],
                "tipo": row["tipo"],
                "vigente": bool(row["vigente"]),
                "creadoEn": row["creado_en"],
            }
            for row in rows
        ]

    def count_active_licenses(self, product_id: str) -> int:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM licencias WHERE producto_id = ? AND vigente = 1",
                (product_id,),
            ).fetchone()
        return int(row["total"])
