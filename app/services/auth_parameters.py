"""Caso de uso FUN-16 / PRC-16: parametrización de autenticación.

Orquesta validación, versionamiento inmutable, auditoría e invalidación de la
caché por versión. Los cambios pasan a ser visibles para los consumidores en la
siguiente petición porque ``value()`` rescuela la versión vigente en cada lectura.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.cache.auth_parameters import AuthParametersCache
from app.core.config import Settings
from app.domain.actor import ADMIN_ROLE, Actor
from app.domain.audit import AuditEvent
from app.domain.auth_parameters import (
    AUTH_MODULO,
    AUTH_PARAMETERS_ENTITY,
    AUTH_PARAMETERS_WRITE_SCOPE,
    DEFINICIONES_POR_CODIGO,
    PREFIJOS_MODULOS_AJENOS,
    SETTING_FIELD_BY_CODE,
    AuthParameterSnapshot,
    AuthParameterVersion,
    validar_dependencias,
    valores_iniciales,
)
from app.domain.exceptions import (
    AuthParameterModuleError,
    AuthParameterNotFoundError,
    AuthParameterVersionNotFoundError,
    AuthParametersForbiddenError,
    InvalidAuthParameterError,
)
from app.repository.audit import SQLiteAuditRepository
from app.repository.auth_parameters import SQLiteAuthParameterRepository


class AuthParametersService:
    def __init__(
        self,
        repository: SQLiteAuthParameterRepository,
        audit_repository: SQLiteAuditRepository,
        cache: AuthParametersCache,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.audit_repository = audit_repository
        self.cache = cache
        self.settings = settings
        self._seed_lock = Lock()

    # ------------------------------------------------------------- accesos
    def _ensure_ready(self) -> AuthParameterVersion:
        version = self.repository.latest()
        if version is not None:
            return version
        with self._seed_lock:
            version = self.repository.latest()
            if version is not None:
                return version
            return self.repository.save(
                valores=valores_iniciales(self.settings),
                anteriores={},
                actor_id="sistema",
                actor_roles=(),
                motivo="version_inicial",
                vigente_desde=datetime.now(timezone.utc),
                modulo=AUTH_MODULO,
            )

    def snapshot(self) -> AuthParameterSnapshot:
        """Instantánea vigente; la caché solo sirve si coincide la versión."""

        version = self._ensure_ready()
        cached = self.cache.get(version.version)
        if cached is not None:
            return cached
        snapshot = version.snapshot()
        self.cache.set(snapshot)
        return snapshot

    def value(self, codigo: str) -> int:
        """Punto de lectura usado por las funciones consumidoras."""

        return self.snapshot().value(codigo)

    def effective_settings(self) -> Settings:
        """``Settings`` con los valores vigentes aplicados a los consumidores."""

        snapshot = self.snapshot()
        overrides = {
            SETTING_FIELD_BY_CODE[codigo]: valor
            for codigo, valor in snapshot.valores.items()
            if codigo in SETTING_FIELD_BY_CODE
        }
        return replace(self.settings, **overrides)

    def current(self) -> AuthParameterVersion:
        return self.repository.latest() or self._ensure_ready()

    def history(self, *, limit: int = 50) -> list[AuthParameterVersion]:
        self._ensure_ready()
        return self.repository.list_versions(limit=limit)

    def get_version(self, version: int) -> AuthParameterVersion:
        self._ensure_ready()
        found = self.repository.get(version)
        if found is None:
            raise AuthParameterVersionNotFoundError(
                f"No existe la versión {version} de los parámetros de autenticación.",
                details={"version": version},
            )
        return found

    # ----------------------------------------------------------- permisos
    @classmethod
    def ensure_admin(cls, actor: Actor) -> None:
        """Guard público para consultas y escrituras administrativas."""

        cls._ensure_admin(actor)

    @staticmethod
    def _ensure_admin(actor: Actor) -> None:
        roles = set(actor.roles)
        # El rol administrador o el alcance explícito de escritura habilitan la
        # operación. Un alcance de otro módulo (p. ej. catalog.category.write)
        # no basta: los módulos no pueden administrar parámetros ajenos.
        if ADMIN_ROLE not in roles and AUTH_PARAMETERS_WRITE_SCOPE not in roles:
            raise AuthParametersForbiddenError(
                "Se requiere el permiso admin.auth.parameters.write para administrar parámetros.",
                details={"actorId": actor.id, "roles": list(actor.roles)},
            )

    # ---------------------------------------------------------- validación
    @staticmethod
    def _validar_modulo(modulo: str) -> None:
        if modulo != AUTH_MODULO:
            raise AuthParameterModuleError(
                "El módulo indicado no corresponde a autenticación.",
                details={"modulo": modulo, "moduloPermitido": AUTH_MODULO},
            )

    @staticmethod
    def _definicion(codigo: str) -> Any:
        definicion = DEFINICIONES_POR_CODIGO.get(codigo)
        if definicion is not None:
            return definicion
        for prefijo, modulo in PREFIJOS_MODULOS_AJENOS.items():
            if codigo.startswith(prefijo):
                raise AuthParameterModuleError(
                    f"El parámetro {codigo} pertenece al módulo {modulo}.",
                    details={
                        "codigo": codigo,
                        "modulo": modulo,
                        "moduloPermitido": AUTH_MODULO,
                    },
                )
        raise AuthParameterNotFoundError(
            f"El parámetro {codigo} no existe en el catálogo de autenticación.",
            details={"codigo": codigo, "modulo": AUTH_MODULO},
        )

    def _validar_cambios(
        self, parametros: dict[str, Any], actual: AuthParameterVersion
    ) -> tuple[dict[str, int], dict[str, int]]:
        if not parametros:
            raise InvalidAuthParameterError(
                "Se requiere al menos un parámetro para actualizar.",
                details={"motivo": "sin_parametros", "versionActual": actual.version},
            )

        errores: list[dict[str, Any]] = []
        nuevos: dict[str, int] = {}
        for codigo, valor in parametros.items():
            definicion = self._definicion(codigo)
            try:
                definicion.validar_valor(valor)
            except InvalidAuthParameterError as exc:
                errores.extend(exc.details.get("errores", []))
                continue
            nuevos[codigo] = valor
        if errores:
            raise InvalidAuthParameterError(
                "Los valores propuestos no son válidos.",
                details={"errores": errores, "versionActual": actual.version},
            )

        fusionados = dict(actual.valores)
        fusionados.update(nuevos)
        try:
            validar_dependencias(fusionados)
        except InvalidAuthParameterError as exc:
            raise InvalidAuthParameterError(
                exc.message,
                details={**exc.details, "versionActual": actual.version},
            ) from exc

        anteriores = {codigo: actual.valores[codigo] for codigo in nuevos}
        return nuevos, anteriores

    # ------------------------------------------------------------ escritura
    def update(
        self,
        actor: Actor,
        *,
        parametros: dict[str, Any],
        modulo: str = AUTH_MODULO,
        motivo: str | None = None,
    ) -> AuthParameterVersion:
        self._ensure_admin(actor)
        self._validar_modulo(modulo)
        actual = self.current()
        nuevos, anteriores = self._validar_cambios(parametros, actual)

        valores = dict(actual.valores)
        valores.update(nuevos)
        fecha = datetime.now(timezone.utc)
        version = self.repository.save(
            valores=valores,
            anteriores=anteriores,
            actor_id=actor.id,
            actor_roles=actor.roles,
            motivo=(motivo or "").strip(),
            vigente_desde=fecha,
            modulo=AUTH_MODULO,
        )
        self.audit_repository.record(
            AuditEvent(
                entidad=AUTH_PARAMETERS_ENTITY,
                entidad_id=f"auth:version-{version.version}",
                accion="parametros_actualizados",
                actor_id=actor.id,
                actor_roles=actor.roles,
                fecha=fecha,
                cambios={
                    "version": version.version,
                    "versionAnterior": actual.version,
                    "modulo": AUTH_MODULO,
                    "motivo": version.motivo,
                    "anteriores": anteriores,
                    "valores": nuevos,
                },
            )
        )
        self.cache.invalidate()
        return version
