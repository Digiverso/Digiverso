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
    LICENSE_CONDITIONS,
    Pagination,
    SignedPayload,
    build_signed_token,
    normalize_filename,
    object_key_for,
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
    """Emite licencias, autoriza descargas y consulta el historial del comprador."""

    def __init__(
        self,
        repository: SQLiteCommerceRepository,
        product_repository: SQLiteProductRepository,
        audit_repository: SQLiteAuditRepository,
        settings: Settings,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.product_repository = product_repository
        self.audit_repository = audit_repository
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(timezone.utc))

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
