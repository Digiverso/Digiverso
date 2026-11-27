"""Persistencia de compras, licencias y descargas de Comercio (HU-15)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.domain.commerce import LICENSE_CONDITIONS, LICENSE_TYPE
from app.domain.exceptions import DownloadLimitError
from app.repository.database import Database


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class SQLiteCommerceRepository:
    """Operaciones atómicas sobre ``compras``, ``licencias`` y ``descargas``."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _purchase(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "productoId": row["producto_id"],
            "compradorId": row["comprador_id"],
            "estado": row["estado"],
            "fechaCreacion": row["fecha_creacion"],
            "fechaPago": row["fecha_pago"],
            "licenciaId": row["licencia_id"],
            "precio": row["precio"],
            "moneda": row["moneda"],
            "archivoClave": row["archivo_clave"],
            "nombreArchivo": row["nombre_archivo"],
        }

    @staticmethod
    def _license(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "productoId": row["producto_id"],
            "compradorId": row["actor_id"],
            "tipo": row["tipo"],
            "vigente": bool(row["vigente"]),
            "fechaEmision": row["creado_en"],
            "condiciones": LICENSE_CONDITIONS,
        }

    def next_purchase_id(self) -> str:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(CAST(substr(id, 5) AS INTEGER)), 0) + 1 AS siguiente "
                "FROM compras WHERE id GLOB 'ord_[0-9]*'"
            ).fetchone()
        return f"ord_{int(row['siguiente']):03d}"

    def register_purchase(
        self,
        product_id: str,
        buyer_id: str,
        *,
        estado: str = "pagada",
        fecha_creacion: datetime,
        fecha_pago: datetime | None = None,
        precio: int = 0,
        moneda: str = "COP",
        archivo_clave: str = "",
        nombre_archivo: str = "",
        purchase_id: str | None = None,
    ) -> dict[str, Any]:
        """Registra una compra; la emisión de licencia es una operación aparte."""

        compra_id = purchase_id or self.next_purchase_id()
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO compras
                    (id, producto_id, comprador_id, estado, fecha_creacion, fecha_pago,
                     licencia_id, precio, moneda, archivo_clave, nombre_archivo)
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)
                """,
                (
                    compra_id,
                    product_id,
                    buyer_id,
                    estado,
                    _iso(fecha_creacion),
                    _iso(fecha_pago) if fecha_pago else None,
                    precio,
                    moneda,
                    archivo_clave,
                    nombre_archivo,
                ),
            )
        compra = self.get_purchase(compra_id)
        assert compra is not None
        return compra

    def get_purchase(self, purchase_id: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM compras WHERE id = ?", (purchase_id,)
            ).fetchone()
        return self._purchase(row) if row is not None else None

    def get_license(self, license_id: str | None) -> dict[str, Any] | None:
        if not license_id:
            return None
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT id, producto_id, actor_id, tipo, vigente, creado_en "
                "FROM licencias WHERE id = ?",
                (license_id,),
            ).fetchone()
        return self._license(row) if row is not None else None

    def active_license_for(
        self, product_id: str, buyer_id: str
    ) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT id, producto_id, actor_id, tipo, vigente, creado_en
                FROM licencias
                WHERE producto_id = ? AND actor_id = ? AND vigente = 1
                ORDER BY id LIMIT 1
                """,
                (product_id, buyer_id),
            ).fetchone()
        return self._license(row) if row is not None else None

    def issue_license(
        self,
        purchase_id: str,
        *,
        fecha_emision: datetime,
        license_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Emite una única licencia para la compra, dentro de una transacción.

        Si la compra ya tiene licencia, la devuelve (idempotencia). Si el par
        producto/comprador ya tiene una licencia vigente, la reutiliza sin
        duplicar el acceso.
        """

        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            compra = connection.execute(
                "SELECT id, producto_id, comprador_id, licencia_id FROM compras WHERE id = ?",
                (purchase_id,),
            ).fetchone()
            if compra is None:
                return None
            if compra["licencia_id"]:
                existente = connection.execute(
                    "SELECT id, producto_id, actor_id, tipo, vigente, creado_en "
                    "FROM licencias WHERE id = ?",
                    (compra["licencia_id"],),
                ).fetchone()
                return self._license(existente) if existente else None

            previa = connection.execute(
                """
                SELECT id, producto_id, actor_id, tipo, vigente, creado_en
                FROM licencias
                WHERE producto_id = ? AND actor_id = ? AND vigente = 1
                ORDER BY id LIMIT 1
                """,
                (compra["producto_id"], compra["comprador_id"]),
            ).fetchone()
            if previa is not None:
                connection.execute(
                    "UPDATE compras SET licencia_id = ? WHERE id = ?",
                    (previa["id"], purchase_id),
                )
                return self._license(previa)

            if license_id is None:
                numero = connection.execute(
                    "SELECT COALESCE(MAX(CAST(substr(id, 5) AS INTEGER)), 0) + 1 AS siguiente "
                    "FROM licencias WHERE id GLOB 'lic_[0-9]*'"
                ).fetchone()
                license_id = f"lic_{int(numero['siguiente']):03d}"
            connection.execute(
                """
                INSERT INTO licencias (id, producto_id, actor_id, tipo, vigente, creado_en)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (
                    license_id,
                    compra["producto_id"],
                    compra["comprador_id"],
                    LICENSE_TYPE,
                    _iso(fecha_emision),
                ),
            )
            connection.execute(
                "UPDATE compras SET licencia_id = ? WHERE id = ?",
                (license_id, purchase_id),
            )
            return {
                "id": license_id,
                "productoId": compra["producto_id"],
                "compradorId": compra["comprador_id"],
                "tipo": LICENSE_TYPE,
                "vigente": True,
                "fechaEmision": _iso(fecha_emision),
                "condiciones": LICENSE_CONDITIONS,
            }

    def count_downloads(self, license_id: str) -> int:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM descargas WHERE licencia_id = ?",
                (license_id,),
            ).fetchone()
        return int(row["total"])

    def reserve_download(
        self,
        *,
        purchase_id: str,
        license_id: str,
        product_id: str,
        actor_id: str,
        ip: str,
        fecha: datetime,
        limite: int,
    ) -> int:
        """Registra la descarga si no se agotó COM-09; devuelve el nuevo total."""

        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            total = int(
                connection.execute(
                    "SELECT COUNT(*) AS total FROM descargas WHERE licencia_id = ?",
                    (license_id,),
                ).fetchone()["total"]
            )
            if total >= limite:
                raise DownloadLimitError(
                    "Se alcanzó el límite de descargas de la licencia.",
                    details={
                        "codigo": "DOWNLOAD_LIMIT_REACHED",
                        "licenciaId": license_id,
                        "limite": limite,
                    },
                )
            connection.execute(
                """
                INSERT INTO descargas
                    (compra_id, licencia_id, producto_id, actor_id, ip, fecha)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (purchase_id, license_id, product_id, actor_id, ip, _iso(fecha)),
            )
            return total + 1

    def history(
        self, buyer_id: str, *, offset: int, limit: int
    ) -> dict[str, Any]:
        """Compras y licencias del comprador, ordenadas por fecha descendente."""

        with self.database.connection() as connection:
            total = int(
                connection.execute(
                    "SELECT COUNT(*) AS total FROM compras WHERE comprador_id = ?",
                    (buyer_id,),
                ).fetchone()["total"]
            )
            compras = connection.execute(
                """
                SELECT c.id, c.producto_id, c.estado,
                       COALESCE(c.fecha_pago, c.fecha_creacion) AS fecha,
                       c.precio, c.moneda, c.licencia_id,
                       l.vigente AS licencia_vigente, l.creado_en AS licencia_fecha
                FROM compras c
                LEFT JOIN licencias l ON l.id = c.licencia_id
                WHERE c.comprador_id = ?
                ORDER BY fecha DESC, c.id DESC
                LIMIT ? OFFSET ?
                """,
                (buyer_id, limit, offset),
            ).fetchall()
            licencias = connection.execute(
                """
                SELECT l.id, l.producto_id, l.actor_id, l.tipo, l.vigente, l.creado_en,
                       c.id AS compra_id, COALESCE(c.fecha_pago, c.fecha_creacion) AS fecha
                FROM licencias l
                JOIN compras c ON c.licencia_id = l.id
                WHERE c.comprador_id = ?
                ORDER BY fecha DESC, l.id DESC
                """,
                (buyer_id,),
            ).fetchall()

        return {
            "total": total,
            "compras": [
                {
                    "id": row["id"],
                    "productoId": row["producto_id"],
                    "estado": row["estado"],
                    "fechaCompra": row["fecha"],
                    "precio": row["precio"],
                    "moneda": row["moneda"],
                    "licenciaId": row["licencia_id"],
                    "estadoLicencia": (
                        "activa" if row["licencia_vigente"] else "inactiva"
                    )
                    if row["licencia_vigente"] is not None
                    else None,
                }
                for row in compras
            ],
            "licencias": [
                {
                    "id": row["id"],
                    "productoId": row["producto_id"],
                    "compradorId": row["actor_id"],
                    "estado": "activa" if row["vigente"] else "inactiva",
                    "condiciones": LICENSE_CONDITIONS,
                    "fechaEmision": row["creado_en"],
                    "compraId": row["compra_id"],
                }
                for row in licencias
            ],
        }

    # ------------------------------------------------------------------ HU-16
    @staticmethod
    def _sale(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "ventaId": row["id"],
            "ordenId": row["orden_id"],
            "productId": row["producto_id"],
            "productorId": row["productor_id"],
            "producto": row["producto"],
            "monto": int(row["monto"]),
            "comision": int(row["comision"]),
            "neto": int(row["neto"]),
            "moneda": row["moneda"],
            "fecha": row["fecha"],
        }

    @staticmethod
    def _payout(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "payoutId": row["id"],
            "productorId": row["productor_id"],
            "periodo": row["periodo"],
            "total": int(row["total"]),
            "moneda": row["moneda"],
            "estado": row["estado"],
            "fechaGeneracion": row["fecha_generacion"],
        }

    def get_sale_by_order(self, order_id: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM ventas WHERE orden_id = ?", (order_id,)
            ).fetchone()
        return self._sale(row) if row is not None else None

    def create_sale(self, sale: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM ventas WHERE orden_id = ?", (sale["ordenId"],)
            ).fetchone()
            if existing is not None:
                return self._sale(existing), False
            numero = connection.execute(
                "SELECT COALESCE(MAX(CAST(substr(id, 6) AS INTEGER)), 0) + 1 AS siguiente "
                "FROM ventas WHERE id GLOB 'sale_[0-9]*'"
            ).fetchone()
            venta_id = sale.get("ventaId") or f"sale_{int(numero['siguiente']):03d}"
            connection.execute(
                """
                INSERT INTO ventas
                    (id, orden_id, producto_id, productor_id, producto, monto, comision, neto, moneda, fecha)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    venta_id,
                    sale["ordenId"],
                    sale["productId"],
                    sale["productorId"],
                    sale["producto"],
                    int(sale["monto"]),
                    int(sale["comision"]),
                    int(sale["neto"]),
                    sale["moneda"],
                    sale["fecha"],
                ),
            )
            row = connection.execute(
                "SELECT * FROM ventas WHERE id = ?", (venta_id,)
            ).fetchone()
        assert row is not None
        return self._sale(row), True

    def list_sales(
        self, producer_id: str, *, offset: int, limit: int
    ) -> dict[str, Any]:
        with self.database.connection() as connection:
            total = int(
                connection.execute(
                    "SELECT COUNT(*) AS total FROM ventas WHERE productor_id = ?",
                    (producer_id,),
                ).fetchone()["total"]
            )
            total_neto = int(
                connection.execute(
                    "SELECT COALESCE(SUM(neto), 0) AS total_neto FROM ventas WHERE productor_id = ?",
                    (producer_id,),
                ).fetchone()["total_neto"]
            )
            rows = connection.execute(
                """
                SELECT * FROM ventas
                WHERE productor_id = ?
                ORDER BY fecha DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (producer_id, limit, offset),
            ).fetchall()
        return {
            "total": total,
            "totalNeto": total_neto,
            "items": [self._sale(row) for row in rows],
        }

    def list_payouts(
        self, producer_id: str, *, offset: int, limit: int
    ) -> dict[str, Any]:
        with self.database.connection() as connection:
            total = int(
                connection.execute(
                    "SELECT COUNT(*) AS total FROM liquidaciones WHERE productor_id = ?",
                    (producer_id,),
                ).fetchone()["total"]
            )
            rows = connection.execute(
                """
                SELECT * FROM liquidaciones
                WHERE productor_id = ?
                ORDER BY fecha_generacion DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (producer_id, limit, offset),
            ).fetchall()
        return {"total": total, "items": [self._payout(row) for row in rows]}

    def eligible_sales_for_payout(
        self, *, producer_id: str, cutoff_iso: str
    ) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT v.*
                FROM ventas v
                LEFT JOIN liquidacion_ventas lv ON lv.venta_id = v.id
                WHERE v.productor_id = ? AND v.fecha <= ? AND lv.venta_id IS NULL
                ORDER BY v.fecha ASC, v.id ASC
                """,
                (producer_id, cutoff_iso),
            ).fetchall()
        return [self._sale(row) for row in rows]

    def list_producers_with_pending_sales(self) -> list[str]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT v.productor_id
                FROM ventas v
                LEFT JOIN liquidacion_ventas lv ON lv.venta_id = v.id
                WHERE lv.venta_id IS NULL
                ORDER BY v.productor_id
                """
            ).fetchall()
        return [str(row["productor_id"]) for row in rows]

    def create_payout(
        self,
        *,
        producer_id: str,
        periodo: str,
        total: int,
        moneda: str,
        fecha_generacion: str,
        sale_ids: list[str],
    ) -> dict[str, Any]:
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            numero = connection.execute(
                "SELECT COALESCE(MAX(CAST(substr(id, 5) AS INTEGER)), 0) + 1 AS siguiente "
                "FROM liquidaciones WHERE id GLOB 'pay_[0-9]*'"
            ).fetchone()
            payout_id = f"pay_{int(numero['siguiente']):03d}"
            connection.execute(
                """
                INSERT INTO liquidaciones
                    (id, productor_id, periodo, total, moneda, estado, fecha_generacion)
                VALUES (?, ?, ?, ?, ?, 'pendiente', ?)
                """,
                (payout_id, producer_id, periodo, int(total), moneda, fecha_generacion),
            )
            for sale_id in sale_ids:
                connection.execute(
                    "INSERT INTO liquidacion_ventas (liquidacion_id, venta_id) VALUES (?, ?)",
                    (payout_id, sale_id),
                )
            row = connection.execute(
                "SELECT * FROM liquidaciones WHERE id = ?", (payout_id,)
            ).fetchone()
        assert row is not None
        return self._payout(row)
