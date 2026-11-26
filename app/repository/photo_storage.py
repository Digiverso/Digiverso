from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Protocol

from app.core.config import Settings


class PhotoStorage(Protocol):
    def guardar(self, cuenta_id: str, contenido: bytes, extension: str) -> str: ...


def construir_clave(cuenta_id: str, contenido: bytes, extension: str) -> str:
    digest = hashlib.sha256(contenido).hexdigest()[:12]
    return f"users/{cuenta_id}/foto-{digest}.{extension}"


def construir_url(base_url: str, clave: str) -> str:
    return f"{base_url.rstrip('/')}/{clave}"


class LocalPhotoStorage:
    def __init__(self, base_path: Path, cdn_base_url: str) -> None:
        self.base_path = Path(base_path)
        self.cdn_base_url = cdn_base_url
        self.base_path.mkdir(parents=True, exist_ok=True)

    def guardar(self, cuenta_id: str, contenido: bytes, extension: str) -> str:
        clave = construir_clave(cuenta_id, contenido, extension)
        destino = self.base_path / clave
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido)
        return construir_url(self.cdn_base_url, clave)


class S3PhotoStorage:
    def __init__(
        self,
        bucket: str,
        cdn_base_url: str,
        region: str,
        endpoint_url: str,
    ) -> None:
        self.bucket = bucket
        self.cdn_base_url = cdn_base_url
        self.region = region
        self.endpoint_url = endpoint_url
        self._client: Any | None = None

    def _obtener_cliente(self) -> Any:
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:
                raise RuntimeError(
                    "PROFILE_PHOTO_BUCKET requiere boto3; instala el cliente S3 de AWS."
                ) from exc
            self._client = boto3.client(
                "s3",
                region_name=self.region,
                endpoint_url=self.endpoint_url or None,
            )
        return self._client

    def guardar(self, cuenta_id: str, contenido: bytes, extension: str) -> str:
        from app.domain.profile import mime_por_formato

        clave = construir_clave(cuenta_id, contenido, extension)
        formato = "jpeg" if extension == "jpg" else extension
        cliente = self._obtener_cliente()
        cliente.put_object(
            Bucket=self.bucket,
            Key=clave,
            Body=contenido,
            ContentType=mime_por_formato(formato),
        )
        return construir_url(self.cdn_base_url, clave)


def build_photo_storage(settings: Settings) -> PhotoStorage:
    if settings.profile_photo_bucket:
        return S3PhotoStorage(
            bucket=settings.profile_photo_bucket,
            cdn_base_url=settings.profile_photo_cdn_base_url,
            region=settings.profile_photo_s3_region,
            endpoint_url=settings.profile_photo_s3_endpoint,
        )
    return LocalPhotoStorage(
        base_path=settings.profile_photo_storage_path,
        cdn_base_url=settings.profile_photo_cdn_base_url,
    )
