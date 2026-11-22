"""Sobre estándar de respuesta usado por todas las HU del marketplace."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    message: str
    data: T
    success: bool = True


def ok(message: str, data: T) -> ApiResponse[T]:
    """Construye una respuesta exitosa con el sobre ``message/data/success``."""

    return ApiResponse(message=message, data=data, success=True)
