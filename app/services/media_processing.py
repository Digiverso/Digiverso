"""Optimización de imágenes y procesamiento de videos (HU-09).

Las imágenes se convierten a WebP cuando Pillow está instalado; si no lo está,
o el archivo no es decodificable, se conserva el original validado por firma. Así la
API no depende de librerías pesadas y sigue cumpliendo CAT-05/CAT-06.
Los videos se dejan intactos: la transcodificación asíncrona se conecta aquí
sustituyendo ``MediaProcessor`` por un adaptador a la cola de trabajos.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ProcessedMedia:
    contenido: bytes
    extension: str


@runtime_checkable
class MediaProcessor(Protocol):
    def process(
        self, contenido: bytes, *, tipo: str, extension: str, formato: str
    ) -> ProcessedMedia:
        ...


class BestEffortMediaProcessor:
    """Convierte imágenes a WebP si es posible; videos sin cambios."""

    def __init__(self, *, webp_quality: int = 82) -> None:
        self.webp_quality = webp_quality

    def process(
        self, contenido: bytes, *, tipo: str, extension: str, formato: str
    ) -> ProcessedMedia:
        del formato
        original = ProcessedMedia(contenido=contenido, extension=extension)
        if tipo != "imagen":
            return original

        try:
            from PIL import Image  # dependencia opcional
        except ImportError:
            return original

        try:
            with Image.open(BytesIO(contenido)) as image:
                image.load()
                modo = "RGBA" if "A" in image.getbands() else "RGB"
                convertida = image.convert(modo)
                buffer = BytesIO()
                convertida.save(buffer, format="WEBP", quality=self.webp_quality, method=6)
            return ProcessedMedia(contenido=buffer.getvalue(), extension="webp")
        except Exception:
            # Un archivo con firma válida pero no decodificable se conserva tal
            # cual: la validación de CAT-05 ya se hizo por firma binaria.
            return original
