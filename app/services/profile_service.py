from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from app.core.config import Settings
from app.domain.auth import Account, UpdatePerfilRequest, UserProfile
from app.domain.profile import (
    InvalidProfileError,
    decodificar_data_url,
    detectar_formato,
    normalizar_formato,
    validar_tamano,
    validar_url_foto,
)
from app.repository.auth_repository import AuthRepository
from app.repository.photo_storage import PhotoStorage


class ProfileService:
    def __init__(
        self,
        repo: AuthRepository,
        settings: Settings,
        photo_storage: PhotoStorage,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repo = repo
        self.settings = settings
        self.photo_storage = photo_storage
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def consultar(self, cuenta: Account) -> UserProfile:
        return UserProfile.from_account(cuenta)

    def actualizar(
        self,
        *,
        cuenta: Account,
        cambios: UpdatePerfilRequest,
        ip: str,
    ) -> UserProfile:
        valores: dict[str, Any] = cambios.model_dump(exclude_unset=True)
        antes = self._snapshot(cuenta)
        despues = dict(antes)

        if "nombre" in valores:
            despues["nombre"] = self._validar_nombre(valores["nombre"])
        if "biografia" in valores:
            despues["biografia"] = self._validar_biografia(valores["biografia"])
        if "foto" in valores:
            despues["foto"] = self._procesar_foto(valores["foto"], cuenta.id)

        actualizada = self.repo.actualizar_perfil(
            cuenta.id,
            nombre=despues["nombre"],
            biografia=despues["biografia"],
            foto=despues["foto"],
        )
        ahora = self.clock()
        campos = [
            campo for campo in ("nombre", "biografia", "foto") if antes[campo] != despues[campo]
        ]
        self.repo.registrar_auditoria(
            "perfil_actualizado",
            cuenta.id,
            ip or "desconocida",
            {
                "usuario": cuenta.id,
                "fecha": ahora.isoformat(),
                "campos": campos,
                "antes": antes,
                "despues": despues,
            },
            ahora,
        )
        return UserProfile.from_account(actualizada or cuenta)

    @staticmethod
    def _snapshot(cuenta: Account) -> dict[str, Any]:
        return {
            "nombre": cuenta.nombre,
            "biografia": cuenta.biografia,
            "foto": cuenta.foto,
        }

    def _validar_nombre(self, valor: object) -> str:
        if not isinstance(valor, str):
            raise InvalidProfileError("El nombre no puede ser nulo.", campo="nombre")
        nombre = valor.strip()
        if not self.settings.profile_name_min_length <= len(nombre) <= self.settings.profile_name_max_length:
            raise InvalidProfileError(
                "El nombre no cumple la longitud permitida.",
                campo="nombre",
                detalles={
                    "minimo": self.settings.profile_name_min_length,
                    "maximo": self.settings.profile_name_max_length,
                },
            )
        return nombre

    def _validar_biografia(self, valor: object) -> str | None:
        if valor is None:
            return None
        if not isinstance(valor, str):
            raise InvalidProfileError("La biografía debe ser texto.", campo="biografia")
        biografia = valor.strip() or None
        if biografia is not None and len(biografia) > self.settings.profile_biografia_max_length:
            raise InvalidProfileError(
                "La biografía excede la longitud permitida.",
                campo="biografia",
                detalles={"maximo": self.settings.profile_biografia_max_length},
            )
        return biografia

    def _procesar_foto(self, valor: object, cuenta_id: str) -> str | None:
        if valor is None:
            return None

        permitidos = tuple(
            normalizar_formato(formato)
            for formato in self.settings.profile_photo_allowed_formats
        )
        if isinstance(valor, bytes):
            contenido = valor
        elif isinstance(valor, str) and valor.lower().startswith("data:"):
            contenido = decodificar_data_url(valor)
        elif isinstance(valor, str):
            return validar_url_foto(valor, permitidos)
        else:
            raise InvalidProfileError(
                "El valor de la foto no es válido.",
                campo="foto",
            )

        validar_tamano(contenido, self.settings.profile_photo_max_bytes)
        _, extension, _ = detectar_formato(contenido, permitidos)
        return self.photo_storage.guardar(cuenta_id, contenido, extension)
