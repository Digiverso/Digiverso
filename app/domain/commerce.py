"""Reglas puras de Comercio: licencias/descargas (HU-15) y ventas/liquidaciones (HU-16)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlsplit

from app.domain.exceptions import (
    ExpiredSignedUrlError,
    InvalidPaginationError,
    InvalidSignedUrlError,
)

LICENSE_CONDITIONS = "Uso personal, sin edición ni reventa"
LICENSE_TYPE = "estandar"

ESTADO_PAGADA = "pagada"

# HU-16
EVENTO_ORDER_PAID = "order.paid"
DEFAULT_COMMISSION_PERCENTAGE = Decimal("15")
DEFAULT_PRODUCER_PERCENTAGE = Decimal("85")
DEFAULT_CURRENCY = "COP"
DEFAULT_PAYOUT_DAYS = 15
DEFAULT_PAYOUT_MINIMUM = 50000


@dataclass(frozen=True)
class SaleAmounts:
    monto: int
    comision: int
    neto: int
    moneda: str


@dataclass(frozen=True)
class SaleRecord:
    venta_id: str
    orden_id: str
    product_id: str
    productor_id: str
    producto: str
    monto: int
    comision: int
    neto: int
    moneda: str
    fecha: datetime


@dataclass(frozen=True)
class PayoutRecord:
    payout_id: str
    productor_id: str
    periodo: str
    total: int
    moneda: str
    estado: str
    fecha_generacion: datetime


def money_int(value: Decimal | int | str) -> int:
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_sale_amounts(
    monto: int,
    *,
    commission_percentage: Decimal | int | str = DEFAULT_COMMISSION_PERCENTAGE,
    producer_percentage: Decimal | int | str = DEFAULT_PRODUCER_PERCENTAGE,
    moneda: str = DEFAULT_CURRENCY,
) -> SaleAmounts:
    monto_decimal = Decimal(int(monto))
    comision_pct = Decimal(str(commission_percentage))
    producer_pct = Decimal(str(producer_percentage))
    # COM-01 drives commission; COM-02 is validated as the commercial agreement.
    comision = money_int(monto_decimal * comision_pct / Decimal("100"))
    neto = money_int(monto_decimal - Decimal(comision))
    esperado = money_int(monto_decimal * producer_pct / Decimal("100"))
    if neto != esperado:
        neto = esperado
        comision = money_int(monto_decimal - Decimal(neto))
    return SaleAmounts(monto=int(monto_decimal), comision=comision, neto=neto, moneda=moneda)


def payout_eligible(fecha_venta: datetime, *, now: datetime, payout_days: int) -> bool:
    venta = fecha_venta.astimezone(timezone.utc)
    limite = venta + timedelta(days=int(payout_days))
    return now.astimezone(timezone.utc) >= limite


@dataclass(frozen=True)
class Pagination:
    pagina: int
    tamanio_pagina: int

    @property
    def offset(self) -> int:
        return (self.pagina - 1) * self.tamanio_pagina


@dataclass(frozen=True)
class SignedPayload:
    object_key: str
    licencia_id: str
    compra_id: str
    expira_en: datetime


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _signature(body: str, secret: str) -> str:
    return _b64encode(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())


def build_signed_token(
    *,
    object_key: str,
    license_id: str,
    purchase_id: str,
    expires_at: datetime,
    secret: str,
) -> str:
    """Devuelve ``payload.firma`` con vencimiento en segundos UNIX."""

    payload: dict[str, Any] = {
        "k": object_key,
        "l": license_id,
        "c": purchase_id,
        "e": int(expires_at.timestamp()),
    }
    body = _b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return f"{body}.{_signature(body, secret)}"


def verify_signed_token(
    token: str, *, secret: str, now: datetime | None = None
) -> SignedPayload:
    """Valida firma y vencimiento; lanza 403 si la firma es inválida o 410 si expiró."""

    try:
        body, firma = token.split(".", 1)
    except (ValueError, AttributeError) as exc:
        raise InvalidSignedUrlError("La URL de descarga no es válida.") from exc

    if not hmac.compare_digest(_signature(body, secret), firma):
        raise InvalidSignedUrlError("La firma de la URL de descarga no es válida.")

    try:
        datos = json.loads(_b64decode(body))
        object_key = str(datos["k"])
        license_id = str(datos["l"])
        purchase_id = str(datos["c"])
        expira = datetime.fromtimestamp(int(datos["e"]), tz=timezone.utc)
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise InvalidSignedUrlError("La URL de descarga no es válida.") from exc

    momento = now or datetime.now(timezone.utc)
    if expira <= momento:
        raise ExpiredSignedUrlError(
            "La URL de descarga expiró.",
            details={"codigo": "URL_EXPIRED", "expiraEn": expira.isoformat()},
        )
    return SignedPayload(
        object_key=object_key,
        licencia_id=license_id,
        compra_id=purchase_id,
        expira_en=expira,
    )


def normalize_filename(nombre: str, media_url: str = "") -> str:
    """Nombre seguro para la descarga, con extensión tomada del medio."""

    sufijo = urlsplit(media_url).path.rsplit("/", 1)[-1]
    extension = ""
    if "." in sufijo:
        candidata = sufijo.rsplit(".", 1)[-1].lower()
        if candidata.isalnum() and 1 <= len(candidata) <= 5:
            extension = f".{candidata}"
    ascii_name = unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "producto"
    return f"{slug}{extension}"


def object_key_for(product_id: str, media_url: str = "") -> str:
    """Clave estable del archivo en almacenamiento."""

    sufijo = urlsplit(media_url).path.rsplit("/", 1)[-1] or "producto.bin"
    sufijo = re.sub(r"[^A-Za-z0-9._-]", "_", sufijo).strip("_") or "producto.bin"
    return f"{product_id}/{sufijo}"


def validate_pagination(
    pagina: Any,
    tamanio_pagina: Any,
    *,
    default_size: int,
    max_size: int,
) -> Pagination:
    """Convierte y valida los parámetros de paginación del historial."""

    try:
        numero = 1 if pagina in (None, "") else int(pagina)
        tamanio = default_size if tamanio_pagina in (None, "") else int(tamanio_pagina)
    except (TypeError, ValueError) as exc:
        raise InvalidPaginationError(
            "Los parámetros de paginación deben ser enteros.",
            details={"codigo": "PAGINATION_INVALID"},
        ) from exc
    if numero < 1 or tamanio < 1 or tamanio > max_size:
        raise InvalidPaginationError(
            "Paginación fuera de rango.",
            details={
                "codigo": "PAGINATION_INVALID",
                "pagina": numero,
                "tamanioPagina": tamanio,
                "maximo": max_size,
            },
        )
    return Pagination(pagina=numero, tamanio_pagina=tamanio)
