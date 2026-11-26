"""Escaneo previo a la publicación de un medio (HU-09).

La implementación incluida es un scanner de firmas peligrosas, suficiente para
rechazar el patrón EICAR y archivos ejecutables disfrazados de imagen/video.
Está detrás del protocolo ``FileScanner`` para poder sustituirlo por un
antivirus real sin tocar el servicio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

_MARKERS: tuple[tuple[bytes, str], ...] = (
    (
        b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE",
        "firma de prueba EICAR detectada",
    ),
    (
        b"X5O!P%@AP[4\\PZX54(P^)7CC)7}",
        "firma de prueba EICAR detectada",
    ),
    (b"<?php", "código PHP incrustado"),
    (b"<script", "script incrustado"),
    (b"javascript:", "script incrustado"),
)


@dataclass(frozen=True)
class ScanResult:
    seguro: bool
    motivo: str = ""


@runtime_checkable
class FileScanner(Protocol):
    def scan(self, contenido: bytes, *, nombre: str = "") -> ScanResult:
        """Devuelve ``seguro=False`` con un motivo si el archivo se rechaza."""
        ...


class SignatureFileScanner:
    """Scanner determinista basado en firmas; sin dependencias externas."""

    def scan(self, contenido: bytes, *, nombre: str = "") -> ScanResult:
        del nombre
        upper = contenido.upper()
        for marker, motivo in _MARKERS:
            if marker in upper:
                return ScanResult(seguro=False, motivo=motivo)

        if contenido.startswith(b"MZ") and b"PE\x00\x00" in contenido[:4096]:
            return ScanResult(seguro=False, motivo="ejecutable Portable Executable detectado")
        if contenido.startswith(b"\x7fELF"):
            return ScanResult(seguro=False, motivo="ejecutable ELF detectado")
        if contenido.lower().startswith(b"#!"):
            return ScanResult(seguro=False, motivo="script ejecutable detectado")

        return ScanResult(seguro=True)
