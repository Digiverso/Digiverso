"""Persistencia SQLite de reportes y sanciones (HU-12).

La evidencia se guarda como JSON en columnas de uso interno; las respuestas se
construyen en la capa de API sin exponer al reportante ni rutas privadas.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.domain.exceptions import DuplicateReportError, ReportNotFoundError
from app.domain.report import (
    ESTADO_ABIERTO,
    Reporte,
    Resolucion,
    Sancion,
)
from app.repository.database import Database


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _json(value: Any, *, default: Any) -> Any:
    try:
        cargado = json.loads(value) if isinstance(value, str) and value else None
    except (TypeError, ValueError):
        cargado = None
    return default if cargado is None else cargado


class ReportRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _next_id(connection: sqlite3.Connection, prefix: str, table: str) -> str:
        fila = connection.execute(
            f"SELECT COALESCE(MAX(CAST(substr(id, {len(prefix) + 1}) AS INTEGER)), 0) "
            f"+ 1 AS siguiente FROM {table} WHERE id GLOB '{prefix}[0-9]*'"
        ).fetchone()
        return f"{prefix}{int(fila['siguiente']):03d}"

    @staticmethod
    def _row_to_report(row: sqlite3.Row) -> Reporte:
        fecha = _datetime(row["fecha"]) or datetime.now(timezone.utc)
        resolucion = Resolucion.from_dict(_json(row["resolucion"], default=None))
        return Reporte(
            id=row["id"],
            contenido_id=row["contenido_id"],
            motivo=row["motivo"],
            evidencia=_json(row["evidencia"], default=[]),
            reportante_id=row["reportante_id"],
            fecha=fecha,
            tipo_contenido=row["tipo_contenido"],
            estado=row["estado"],
            evidencia_hash=row["evidencia_hash"] or "",
            resolucion=resolucion,
            metadatos=_json(row["metadatos"], default={}),
        )

    @staticmethod
    def _row_to_sanction(row: sqlite3.Row) -> Sancion:
        return Sancion(
            id=row["id"],
            contenido_id=row["contenido_id"],
            tipo=row["tipo"],
            duracion_dias=int(row["duracion_dias"] or 0),
            usuario_afectado=row["usuario_afectado"],
            fecha=_datetime(row["fecha"]) or datetime.now(timezone.utc),
            reporte_id=row["reporte_id"],
            motivo=row["motivo"] or "",
            observacion=row["observacion"] or "",
            evidencia=_json(row["evidencia"], default=[]),
            evidencia_hash=row["evidencia_hash"] or "",
            accion_contenido=row["accion_contenido"],
            apelable=bool(row["apelable"]),
            notificado=bool(row["notificado"]),
            estado_contenido=row["estado_contenido"],
        )

    # ------------------------------------------------------------- reportes
    def has_open(self, reportante_id: str, contenido_id: str) -> bool:
        with self.database.connection() as connection:
            fila = connection.execute(
                """
                SELECT 1 FROM reportes
                WHERE reportante_id = ? AND contenido_id = ?
                  AND estado IN ('abierto', 'en_revision')
                LIMIT 1
                """,
                (reportante_id, contenido_id),
            ).fetchone()
        return fila is not None

    def save(self, reporte: Reporte) -> Reporte:
        with self.database.connection() as connection:
            identificador = reporte.id or self._next_id(connection, "rep_", "reportes")
            try:
                connection.execute(
                    """
                    INSERT INTO reportes
                        (id, contenido_id, tipo_contenido, motivo, evidencia,
                         evidencia_hash, reportante_id, estado, fecha, metadatos)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        identificador,
                        reporte.contenido_id,
                        reporte.tipo_contenido,
                        reporte.motivo,
                        json.dumps(reporte.evidencia, ensure_ascii=False, default=str),
                        reporte.evidencia_hash,
                        reporte.reportante_id,
                        reporte.estado or ESTADO_ABIERTO,
                        _iso(reporte.fecha),
                        json.dumps(reporte.metadatos, ensure_ascii=False, default=str),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateReportError(
                    "Ya existe un reporte abierto del mismo usuario sobre este contenido.",
                    details={
                        "codigo": "REPORT_DUPLICATE",
                        "contenidoId": reporte.contenido_id,
                    },
                ) from exc
        reporte.id = identificador
        return reporte

    def get(self, reporte_id: str) -> Reporte | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM reportes WHERE id = ?", (reporte_id,)
            ).fetchone()
        return self._row_to_report(row) if row else None

    def get_or_raise(self, reporte_id: str) -> Reporte:
        reporte = self.get(reporte_id)
        if reporte is None:
            raise ReportNotFoundError(
                "No existe el reporte solicitado.",
                details={"codigo": "REPORT_NOT_FOUND", "id": reporte_id},
            )
        return reporte

    def list(
        self,
        *,
        estado: str | None = None,
        contenido_id: str | None = None,
        motivo: str | None = None,
        reportante_id: str | None = None,
        limite: int = 20,
        offset: int = 0,
    ) -> tuple[list[Reporte], int]:
        condiciones: list[str] = []
        parametros: list[Any] = []
        if estado:
            condiciones.append("estado = ?")
            parametros.append(estado)
        if contenido_id:
            condiciones.append("contenido_id = ?")
            parametros.append(contenido_id)
        if motivo:
            condiciones.append("motivo = ?")
            parametros.append(motivo)
        if reportante_id:
            condiciones.append("reportante_id = ?")
            parametros.append(reportante_id)
        where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        with self.database.connection() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) AS total FROM reportes {where}", parametros
            ).fetchone()["total"]
            rows = connection.execute(
                f"SELECT * FROM reportes {where} "
                "ORDER BY fecha DESC, id DESC LIMIT ? OFFSET ?",
                (*parametros, limite, offset),
            ).fetchall()
        return [self._row_to_report(row) for row in rows], int(total)

    def update(self, reporte: Reporte) -> Reporte:
        with self.database.connection() as connection:
            connection.execute(
                """
                UPDATE reportes SET
                    estado = ?, resolucion = ?, fecha_resolucion = ?, evidencia = ?
                WHERE id = ?
                """,
                (
                    reporte.estado,
                    json.dumps(reporte.resolucion.to_dict(), ensure_ascii=False)
                    if reporte.resolucion
                    else None,
                    _iso(reporte.resolucion.fecha) if reporte.resolucion else None,
                    json.dumps(reporte.evidencia, ensure_ascii=False, default=str),
                    reporte.id,
                ),
            )
        return reporte

    # ------------------------------------------------------------ sanciones
    def save_sanction(self, sancion: Sancion) -> Sancion:
        with self.database.connection() as connection:
            identificador = sancion.id or self._next_id(connection, "san_", "sanciones")
            connection.execute(
                """
                INSERT INTO sanciones
                    (id, reporte_id, contenido_id, tipo, duracion_dias,
                     usuario_afectado, motivo, observacion, evidencia,
                     evidencia_hash, accion_contenido, apelable, notificado,
                     estado_contenido, fecha)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identificador,
                    sancion.reporte_id,
                    sancion.contenido_id,
                    sancion.tipo,
                    sancion.duracion_dias,
                    sancion.usuario_afectado,
                    sancion.motivo,
                    sancion.observacion,
                    json.dumps(sancion.evidencia, ensure_ascii=False, default=str),
                    sancion.evidencia_hash,
                    sancion.accion_contenido,
                    int(sancion.apelable),
                    int(sancion.notificado),
                    sancion.estado_contenido,
                    _iso(sancion.fecha),
                ),
            )
        sancion.id = identificador
        return sancion

    def update_sanction(self, sancion: Sancion) -> Sancion:
        with self.database.connection() as connection:
            connection.execute(
                """
                UPDATE sanciones SET notificado = ?, estado_contenido = ? WHERE id = ?
                """,
                (int(sancion.notificado), sancion.estado_contenido, sancion.id),
            )
        return sancion

    def get_sanction(self, sancion_id: str) -> Sancion | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM sanciones WHERE id = ?", (sancion_id,)
            ).fetchone()
        return self._row_to_sanction(row) if row else None

    def list_sanctions(
        self, *, reporte_id: str | None = None, usuario_afectado: str | None = None
    ) -> list[Sancion]:
        condiciones: list[str] = []
        parametros: list[Any] = []
        if reporte_id:
            condiciones.append("reporte_id = ?")
            parametros.append(reporte_id)
        if usuario_afectado:
            condiciones.append("usuario_afectado = ?")
            parametros.append(usuario_afectado)
        where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        with self.database.connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM sanciones {where} ORDER BY fecha DESC, id DESC",
                parametros,
            ).fetchall()
        return [self._row_to_sanction(row) for row in rows]
