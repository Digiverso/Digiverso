"""Casos de uso FUN-44 a FUN-47: licencia, descarga e historial (HU-15)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.core.config import Settings
from app.domain.actor import Actor
from app.domain.audit import AuditEvent
from app.domain.auth import Account
from app.domain.commerce import (
    ESTADO_PAGADA,
    EVENTO_ORDER_PAID,
    LICENSE_CONDITIONS,
    Pagination,
    SignedPayload,
    build_signed_token,
    calculate_sale_amounts,
    normalize_filename,
    object_key_for,
    payout_eligible,
    validate_pagination,
    verify_signed_token,
)
from app.domain.exceptions import (
    InvalidPurchaseStateError,
    LicenseForbiddenError,
    LicenseNotFoundError,
    LicenseRequiredError,
    PurchaseNotFoundError,
    ProductNotFoundError,
)
from app.services.notifications import NotificationPublisher
from app.repository.audit import SQLiteAuditRepository
from app.repository.commerce import SQLiteCommerceRepository
from app.repository.products import SQLiteProductRepository

Principal = Actor | Account

DOWNLOADS_PATH = "/api/v1/commerce/downloads"


@dataclass(frozen=True)
class DownloadResult:
    url: str
    expira_en: datetime
    nombre_archivo: str


class CommerceService:
    """HU-15 licencias/descargas/historial y HU-16 ventas/liquidaciones."""

    def __init__(
        self,
        repository: SQLiteCommerceRepository,
        product_repository: SQLiteProductRepository,
        audit_repository: SQLiteAuditRepository,
        settings: Settings,
        clock: Callable[[], datetime] | None = None,
        notifier: NotificationPublisher | None = None,
    ) -> None:
        self.repository = repository
        self.product_repository = product_repository
        self.audit_repository = audit_repository
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.notifier = notifier

    @staticmethod
    def _actor_id(actor: Principal) -> str:
        return actor.id

    @staticmethod
    def _roles(actor: Principal) -> tuple[str, ...]:
        if isinstance(actor, Account):
            return (actor.rol.value,)
        return actor.roles

    @staticmethod
    def _ensure_owner(buyer_id: str, actor: Principal) -> None:
        if buyer_id != actor.id:
            raise LicenseForbiddenError(
                "La licencia o compra pertenece a otro consumidor.",
                details={
                    "codigo": "LICENSE_FORBIDDEN",
                    "compradorId": buyer_id,
                    "actorId": actor.id,
                },
            )

    # -------------------------------------------------------------- FUN-44
    def register_paid_purchase(
        self,
        product_id: str,
        buyer_id: str,
        *,
        fecha: datetime | None = None,
        precio: int | None = None,
    ) -> dict[str, Any]:
        """Registra una compra pagada (llamada por la confirmación de pago).

        HU-14 no está integrada en esta rama; este método es el punto de entrada
        que ese módulo invocará tras confirmar el webhook, sin duplicar el cobro.
        """

        product = self.product_repository.get(product_id)
        if product is None:
            raise ProductNotFoundError(
                "El producto no existe.", details={"id": product_id}
            )
        ahora = fecha or self.clock()
        medio = next((item for item in product.medios if getattr(item, "url", "")), None)
        media_url = getattr(medio, "url", "") if medio else ""
        return self.repository.register_purchase(
            product_id,
            buyer_id,
            estado=ESTADO_PAGADA,
            fecha_creacion=ahora,
            fecha_pago=ahora,
            precio=product.precio if precio is None else precio,
            moneda=product.moneda,
            archivo_clave=object_key_for(product_id, media_url),
            nombre_archivo=normalize_filename(product.nombre, media_url),
        )

    def emit_license(self, purchase_id: str) -> dict[str, Any]:
        """Emite una licencia solo si la orden está pagada; es idempotente."""

        compra = self.repository.get_purchase(purchase_id)
        if compra is None:
            raise PurchaseNotFoundError(
                "La compra no existe.", details={"id": purchase_id}
            )
        if compra["estado"] != ESTADO_PAGADA:
            raise InvalidPurchaseStateError(
                "Solo una orden pagada puede generar licencia.",
                details={"codigo": "ORDER_NOT_PAID", "ordenId": purchase_id},
            )
        if compra["licenciaId"]:
            licencia = self.repository.get_license(compra["licenciaId"])
            if licencia is not None:
                return self._license_response(licencia)

        licencia = self.repository.issue_license(
            purchase_id, fecha_emision=self.clock()
        )
        if licencia is None:
            raise PurchaseNotFoundError(
                "La compra no existe.", details={"id": purchase_id}
            )
        self.audit_repository.record(
            AuditEvent(
                entidad="licencia",
                entidad_id=licencia["id"],
                accion="licencia_emitida",
                actor_id=compra["compradorId"],
                actor_roles=(),
                fecha=self.clock(),
                cambios={
                    "ordenId": purchase_id,
                    "productoId": compra["productoId"],
                    "condiciones": LICENSE_CONDITIONS,
                },
            )
        )
        return self._license_response(licencia)

    # -------------------------------------------------------------- FUN-45
    @staticmethod
    def _license_response(licencia: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": licencia["id"],
            "productoId": licencia["productoId"],
            "compradorId": licencia["compradorId"],
            "estado": "activa" if licencia["vigente"] else "inactiva",
            "condiciones": licencia["condiciones"],
            "fechaEmision": licencia["fechaEmision"],
        }

    def get_license(self, license_id: str, actor: Principal) -> dict[str, Any]:
        licencia = self.repository.get_license(license_id)
        if licencia is None:
            raise LicenseNotFoundError(
                "La licencia no existe.", details={"id": license_id}
            )
        self._ensure_owner(licencia["compradorId"], actor)
        return self._license_response(licencia)

    # -------------------------------------------------------------- FUN-46
    def _signing_secret(self) -> str:
        return self.settings.commerce_download_signing_secret or self.settings.secret_key

    def download(
        self,
        purchase_id: str,
        actor: Principal,
        *,
        ip: str,
        base_url: str = "",
    ) -> DownloadResult:
        compra = self.repository.get_purchase(purchase_id)
        if compra is None:
            raise PurchaseNotFoundError(
                "La compra no existe.", details={"id": purchase_id}
            )
        self._ensure_owner(compra["compradorId"], actor)

        licencia = self.repository.get_license(compra["licenciaId"])
        if licencia is None or not licencia["vigente"]:
            raise LicenseRequiredError(
                "La descarga requiere una licencia activa.",
                details={"codigo": "LICENSE_REQUIRED", "ordenId": purchase_id},
            )
        self._ensure_owner(licencia["compradorId"], actor)

        ahora = self.clock()
        expira_en = ahora + timedelta(
            minutes=self.settings.commerce_download_ttl_minutes
        )
        token = build_signed_token(
            object_key=compra["archivoClave"],
            license_id=licencia["id"],
            purchase_id=purchase_id,
            expires_at=expira_en,
            secret=self._signing_secret(),
        )
        total = self.repository.reserve_download(
            purchase_id=purchase_id,
            license_id=licencia["id"],
            product_id=compra["productoId"],
            actor_id=actor.id,
            ip=ip,
            fecha=ahora,
            limite=self.settings.commerce_max_downloads,
        )
        self.audit_repository.record(
            AuditEvent(
                entidad="descarga",
                entidad_id=purchase_id,
                accion="descarga_autorizada",
                actor_id=actor.id,
                actor_roles=self._roles(actor),
                fecha=ahora,
                cambios={
                    "licenciaId": licencia["id"],
                    "productoId": compra["productoId"],
                    "ip": ip,
                    "expiraEn": expira_en.isoformat(),
                    "descargaNumero": total,
                },
            )
        )
        url = f"{base_url.rstrip('/')}{DOWNLOADS_PATH}/{token}" if base_url else (
            f"{DOWNLOADS_PATH}/{token}"
        )
        return DownloadResult(
            url=url,
            expira_en=expira_en,
            nombre_archivo=compra["nombreArchivo"],
        )

    def resolve_download(
        self, token: str, *, now: datetime | None = None
    ) -> SignedPayload:
        """Valida la URL firmada antes de entregar el objeto desde S3."""

        return verify_signed_token(
            token, secret=self._signing_secret(), now=now or self.clock()
        )

    def storage_url(self, object_key: str) -> str:
        base = self.settings.commerce_storage_base_url.rstrip("/")
        return f"{base}/{object_key.lstrip('/')}"

    # -------------------------------------------------------------- FUN-47
    def history(
        self,
        actor: Principal,
        *,
        pagina: Any = None,
        tamanio_pagina: Any = None,
    ) -> dict[str, Any]:
        paginacion: Pagination = validate_pagination(
            pagina,
            tamanio_pagina,
            default_size=self.settings.commerce_default_page_size,
            max_size=self.settings.commerce_max_page_size,
        )
        datos = self.repository.history(
            self._actor_id(actor),
            offset=paginacion.offset,
            limit=paginacion.tamanio_pagina,
        )
        total = int(datos["total"])
        return {
            **datos,
            "pagina": paginacion.pagina,
            "tamanioPagina": paginacion.tamanio_pagina,
            "totalPaginas": (
                (total + paginacion.tamanio_pagina - 1) // paginacion.tamanio_pagina
            ),
        }

    # -------------------------------------------------------------- HU-16
    def register_sale_from_order_paid(self, payload: dict[str, Any]) -> dict[str, Any]:
        orden_id = str(payload.get("ordenId") or payload.get("orderId") or "").strip()
        estado = str(payload.get("estado") or ESTADO_PAGADA).strip().lower()
        if not orden_id:
            raise InvalidPurchaseStateError("La orden pagada es inválida.", details={"codigo": "ORDER_NOT_PAID"})
        if estado != ESTADO_PAGADA:
            raise InvalidPurchaseStateError(
                "Solo una orden pagada puede registrar una venta.",
                details={"codigo": "ORDER_NOT_PAID", "ordenId": orden_id, "estado": estado},
            )

        product_id = str(payload.get("productId") or payload.get("productoId") or "").strip()
        monto = int(payload.get("monto") or payload.get("precio") or 0)
        fecha_raw = payload.get("fecha") or payload.get("paidAt")
        fecha = self.clock() if not fecha_raw else datetime.fromisoformat(str(fecha_raw).replace("Z", "+00:00"))
        moneda = str(payload.get("moneda") or self.settings.commerce_currency).upper()

        product = self.product_repository.get(product_id)
        if product is None:
            raise ProductNotFoundError("El producto no existe.", details={"id": product_id})

        amounts = calculate_sale_amounts(
            monto,
            commission_percentage=self.settings.commerce_commission_percentage,
            producer_percentage=self.settings.commerce_producer_percentage,
            moneda=moneda,
        )
        sale, created = self.repository.create_sale(
            {
                "ordenId": orden_id,
                "productId": product_id,
                "productorId": product.autor_id,
                "producto": product.nombre,
                "monto": amounts.monto,
                "comision": amounts.comision,
                "neto": amounts.neto,
                "moneda": amounts.moneda,
                "fecha": fecha.astimezone(timezone.utc).isoformat(),
            }
        )

        if created:
            self.audit_repository.record(
                AuditEvent(
                    entidad="venta",
                    entidad_id=sale["ventaId"],
                    accion="venta_registrada",
                    actor_id=product.autor_id,
                    actor_roles=("productor",),
                    fecha=self.clock(),
                    cambios={
                        "ordenId": sale["ordenId"],
                        "productId": sale["productId"],
                        "monto": sale["monto"],
                        "comision": sale["comision"],
                        "neto": sale["neto"],
                        "moneda": sale["moneda"],
                    },
                )
            )
            if self.notifier is not None:
                try:
                    self.notifier.notificar_evento(
                        cuenta_id=product.autor_id,
                        tipo="venta_registrada",
                        contexto={
                            "producto": sale["producto"],
                            "monto_neto": sale["neto"],
                            "fecha": sale["fecha"],
                            "detalle": f"Monto neto: {sale['neto']} {sale['moneda']}. Fecha: {sale['fecha']}.",
                        },
                        clave_idempotencia=f"sale:{sale['ordenId']}:{sale['productorId']}",
                        nombre=product.autor_nombre or "",
                    )
                except Exception:
                    pass
        return sale

    def handle_order_paid(self, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        data = dict(payload or {})
        data.update(kwargs)
        return self.register_sale_from_order_paid(data)

    def list_sales(self, actor: Principal, *, pagina: Any = None, tamanio_pagina: Any = None) -> dict[str, Any]:
        paginacion = validate_pagination(
            pagina,
            tamanio_pagina,
            default_size=self.settings.commerce_default_page_size,
            max_size=self.settings.commerce_max_page_size,
        )
        datos = self.repository.list_sales(
            self._actor_id(actor), offset=paginacion.offset, limit=paginacion.tamanio_pagina
        )
        total = int(datos["total"])
        return {
            **datos,
            "pagina": paginacion.pagina,
            "tamanioPagina": paginacion.tamanio_pagina,
            "totalPaginas": (total + paginacion.tamanio_pagina - 1) // paginacion.tamanio_pagina,
        }

    def list_payouts(self, actor: Principal, *, pagina: Any = None, tamanio_pagina: Any = None) -> dict[str, Any]:
        paginacion = validate_pagination(
            pagina,
            tamanio_pagina,
            default_size=self.settings.commerce_default_page_size,
            max_size=self.settings.commerce_max_page_size,
        )
        datos = self.repository.list_payouts(
            self._actor_id(actor), offset=paginacion.offset, limit=paginacion.tamanio_pagina
        )
        total = int(datos["total"])
        return {
            **datos,
            "pagina": paginacion.pagina,
            "tamanioPagina": paginacion.tamanio_pagina,
            "totalPaginas": (total + paginacion.tamanio_pagina - 1) // paginacion.tamanio_pagina,
        }

    def generar_liquidaciones(self, *, now: datetime | None = None) -> dict[str, Any]:
        momento = now or self.clock()
        cutoff = (momento.astimezone(timezone.utc) - timedelta(days=int(self.settings.commerce_payout_days))).isoformat()
        generadas: list[dict[str, Any]] = []
        omitidas: list[dict[str, Any]] = []
        for producer_id in self.repository.list_producers_with_pending_sales():
            elegibles = self.repository.eligible_sales_for_payout(producer_id=producer_id, cutoff_iso=cutoff)
            total = sum(int(s["neto"]) for s in elegibles)
            if not elegibles:
                continue
            if total < int(self.settings.commerce_payout_minimum):
                omitidas.append(
                    {
                        "productorId": producer_id,
                        "motivo": "MINIMO_NO_ALCANZADO",
                        "totalElegible": total,
                        "minimo": int(self.settings.commerce_payout_minimum),
                    }
                )
                continue
            payout = self.repository.create_payout(
                producer_id=producer_id,
                periodo=momento.astimezone(timezone.utc).strftime("%Y-%m"),
                total=total,
                moneda=elegibles[0]["moneda"],
                fecha_generacion=momento.astimezone(timezone.utc).isoformat(),
                sale_ids=[s["ventaId"] for s in elegibles],
            )
            self.audit_repository.record(
                AuditEvent(
                    entidad="liquidacion",
                    entidad_id=payout["payoutId"],
                    accion="liquidacion_generada",
                    actor_id=producer_id,
                    actor_roles=("productor",),
                    fecha=momento,
                    cambios={"total": payout["total"], "periodo": payout["periodo"], "ventas": len(elegibles)},
                )
            )
            generadas.append(payout)
        return {"generadas": generadas, "omitidas": omitidas}

    def exportar_ventas_csv(self, actor: Principal) -> str:
        datos = self.repository.list_sales(self._actor_id(actor), offset=0, limit=10000)
        lines = ["ventaId,ordenId,productId,producto,monto,comision,neto,moneda,fecha"]
        for item in datos["items"]:
            producto = str(item["producto"]).replace('"', '""')
            lines.append(
                f"{item['ventaId']},{item['ordenId']},{item['productId']},\"{producto}\",{item['monto']},{item['comision']},{item['neto']},{item['moneda']},{item['fecha']}"
            )
        return "\n".join(lines) + "\n"
