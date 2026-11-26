"""Almacenamiento de archivos de medios (HU-09)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from app.core.config import Settings


@runtime_checkable
class MediaStorage(Protocol):
    def save(
        self, product_id: str, media_id: str, contenido: bytes, extension: str
    ) -> str:
        """Guarda el archivo y devuelve la URL pública del medio."""
        ...

    def remove(self, url: str) -> None:
        """Elimina el archivo físico (no usado por el borrado lógico)."""
        ...


def _segmento_seguro(valor: str) -> str:
    if not valor or any(caracter in valor for caracter in ("/", "\\", "..")):
        raise ValueError("Identificador de medio inseguro.")
    return valor


class LocalMediaStorage:
    """Guarda en disco y expone URLs construidas con ``MEDIA_URL_BASE``."""

    def __init__(self, settings: Settings) -> None:
        directorio = settings.media_storage_dir.expanduser()
        self.directorio = directorio if directorio.is_absolute() else Path.cwd() / directorio
        self.url_base = settings.media_url_base.rstrip("/")

    def save(
        self, product_id: str, media_id: str, contenido: bytes, extension: str
    ) -> str:
        producto = _segmento_seguro(product_id)
        medio = _segmento_seguro(media_id)
        nombre = f"{medio}.{extension.lstrip('.').lower()}"
        subcarpeta = self.directorio / producto
        subcarpeta.mkdir(parents=True, exist_ok=True)
        (subcarpeta / nombre).write_bytes(contenido)
        return f"{self.url_base}/{producto}/{nombre}"

    def remove(self, url: str) -> None:
        nombre = url.rsplit("/", 1)[-1]
        producto = url.rsplit("/", 2)[-2]
        ruta = self.directorio / _segmento_seguro(producto) / _segmento_seguro(nombre)
        if ruta.exists():
            ruta.unlink()
