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


# ------------------------------------------------------------------ HU-12
class InvalidReportError(CatalogError):
    """Motivo CAT-14, evidencia o decisión de reporte inválidos."""

    status_code = 400
    code = "REPORT_INVALID"


class DuplicateReportError(CatalogError):
    """Ya existe un reporte abierto del mismo usuario sobre el mismo contenido."""

    status_code = 409
    code = "REPORT_DUPLICATE"


class ReportNotFoundError(CatalogError):
    status_code = 404
    code = "REPORT_NOT_FOUND"


class ReportInvalidStateError(CatalogError):
    status_code = 409
    code = "REPORT_INVALID_STATE"


class ReportForbiddenError(ForbiddenError):
    """Solo un administrador puede gestionar reportes y sanciones."""

    code = "REPORT_FORBIDDEN"


class InvalidSanctionError(CatalogError):
    """Tipo CAT-15 o duración CAT-16 inválidos."""

    status_code = 400
    code = "SANCTION_INVALID"
