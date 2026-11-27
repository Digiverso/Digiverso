"""Errores de dominio del catálogo y su traducción a HTTP."""

from __future__ import annotations

from typing import Any


class CatalogError(Exception):
    """Base de los errores de negocio del catálogo."""

    status_code: int = 400
    code: str = "CATALOG_ERROR"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ForbiddenError(CatalogError):
    status_code = 403
    code = "CATALOG_FORBIDDEN"


class InvalidCategoryError(CatalogError):
    status_code = 422
    code = "CATEGORY_INVALID"


class CategoryNotFoundError(CatalogError):
    status_code = 404
    code = "CATEGORY_NOT_FOUND"


class DuplicateCategoryNameError(CatalogError):
    status_code = 409
    code = "CATEGORY_DUPLICATE"


class InvalidParentError(CatalogError):
    status_code = 400
    code = "CATEGORY_INVALID_PARENT"


class CategoryCycleError(CatalogError):
    status_code = 400
    code = "CATEGORY_CYCLE"


class CategoryHasActiveProductsError(CatalogError):
    status_code = 409
    code = "CATEGORY_ACTIVE_PRODUCTS"


# ------------------------------------------------------------------ HU-08
class InvalidProductError(CatalogError):
    status_code = 422
    code = "PRODUCT_INVALID"


class InsufficientProductMediaError(InvalidProductError):
    code = "PRODUCT_MEDIA_REQUIRED"


class ProductNotFoundError(CatalogError):
    status_code = 404
    code = "PRODUCT_NOT_FOUND"


class InvalidProductStateError(CatalogError):
    status_code = 409
    code = "PRODUCT_INVALID_STATE"


# ------------------------------------------------------------------ HU-09
class MediaFileRequiredError(CatalogError):
    status_code = 400
    code = "MEDIA_FILE_REQUIRED"


class InvalidMediaFormatError(CatalogError):
    status_code = 400
    code = "MEDIA_FORMAT_INVALID"


class MediaTooLargeError(CatalogError):
    status_code = 413
    code = "MEDIA_TOO_LARGE"


class MediaLimitError(CatalogError):
    status_code = 409
    code = "MEDIA_LIMIT_REACHED"


class MediaScanError(CatalogError):
    status_code = 400
    code = "MEDIA_SCAN_REJECTED"


class MediaNotFoundError(CatalogError):
    status_code = 404
    code = "MEDIA_NOT_FOUND"


# ------------------------------------------------------------------ HU-06
class InvalidAuthParameterError(CatalogError):
    """Parámetro de autenticación inválido (rango, tipo o dependencia)."""

    status_code = 400
    code = "AUTH_PARAMETER_INVALID"


# Alias descriptivo para la familia de errores de parametrización.
AuthParameterError = InvalidAuthParameterError


class AuthParameterModuleError(AuthParameterError):
    code = "AUTH_PARAMETER_MODULE"


class AuthParameterNotFoundError(AuthParameterError):
    code = "AUTH_PARAMETER_NOT_FOUND"


class AuthParametersForbiddenError(ForbiddenError):
    code = "AUTH_PARAMETERS_FORBIDDEN"


class AuthParameterVersionNotFoundError(CatalogError):
    status_code = 404
    code = "AUTH_PARAMETER_VERSION_NOT_FOUND"


# ------------------------------------------------------------------ HU-10
class InvalidCatalogQueryError(CatalogError):
    status_code = 422
    code = "CATALOG_QUERY_INVALID"


# ------------------------------------------------------------------ HU-11
class InvalidPublicationReviewError(CatalogError):
    """Checklist incompleto, motivo CAT-14 inválido u observación ausente."""

    status_code = 400
    code = "REVIEW_DECISION_INVALID"


class ReviewForbiddenError(ForbiddenError):
    """El actor no es administrador o revisa un producto de su autoría."""

    code = "REVIEW_FORBIDDEN"


# ------------------------------------------------------------------ HU-15
class ConsumerRequiredError(CatalogError):
    """La operación de Comercio requiere un comprador autenticado."""

    status_code = 401
    code = "CONSUMER_REQUIRED"


class LicenseNotFoundError(CatalogError):
    status_code = 404
    code = "LICENSE_NOT_FOUND"


class PurchaseNotFoundError(CatalogError):
    status_code = 404
    code = "PURCHASE_NOT_FOUND"


class LicenseForbiddenError(ForbiddenError):
    """La licencia o compra pertenece a otro consumidor."""

    code = "LICENSE_FORBIDDEN"


class LicenseRequiredError(ForbiddenError):
    """La compra no tiene licencia activa para el consumidor."""

    code = "LICENSE_REQUIRED"


class DownloadLimitError(ForbiddenError):
    code = "DOWNLOAD_LIMIT_REACHED"


class InvalidPurchaseStateError(CatalogError):
    """Solo una orden pagada puede generar licencia."""

    status_code = 409
    code = "ORDER_NOT_PAID"


class DuplicateLicenseError(CatalogError):
    status_code = 409
    code = "LICENSE_ALREADY_ACTIVE"


class InvalidSignedUrlError(ForbiddenError):
    code = "SIGNATURE_INVALID"


class ExpiredSignedUrlError(ForbiddenError):
    status_code = 410
    code = "URL_EXPIRED"


class InvalidPaginationError(CatalogError):
    status_code = 400
    code = "PAGINATION_INVALID"
