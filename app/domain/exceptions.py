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
