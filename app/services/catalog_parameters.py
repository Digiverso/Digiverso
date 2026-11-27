"""Caso de uso FUN-39 / PRC-39: parametrización del catálogo.

Orquesta validación, versionamiento inmutable, auditoría e invalidación de la
caché por versión. Los consumidores leen los valores vigentes a través de
``settings_view``: cada acceso a un campo CAT resuelve la versión actual, por
lo que un cambio se aplica en la siguiente petición sin recrear servicios.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.cache.catalog_parameters import CatalogParametersCache
from app.core.config import Settings
from app.domain.actor import ADMIN_ROLE, Actor
from app.domain.audit import AuditEvent
from app.domain.catalog_parameters import (
    CATALOG_MODULO,
    CATALOG_PARAMETERS_ENTITY,
    CATALOG_PARAMETERS_WRITE_SCOPE,
    CODIGO_BY_SETTING_FIELD,
    DEFINICIONES_POR_CODIGO,
    MODULOS_AJENOS,
    CatalogParameterSnapshot,
    CatalogParameterVersion,
    validar_dependencias,
    valores_iniciales,
)
from app.domain.catalog_parameter_exceptions import (
    CatalogParameterModuleError,
    CatalogParameterNotFoundError,
    CatalogParameterVersionNotFoundError,
    CatalogParametersForbiddenError,
    InvalidCatalogParameterError,
)
from app.repository.audit import SQLiteAuditRepository
from app.repository.catalog_parameters import SQLiteCatalogParameterRepository


class CatalogSettingsView:
    """Vista de ``Settings`` que relee la versión vigente en cada acceso.

    Los campos que no pertenecen al catálogo se delegan al objeto original;
    las listas se convierten en tupla cuando el campo esperado es una tupla.
    """

    def __init__(self, provider: "CatalogParametersService", base: Settings) -> None:
        object.__setattr__(self, "_provider", provider)
        object.__setattr__(self, "_base", base)

    def __getattr__(self, name: str) -> Any:
        codigo = CODIGO_BY_SETTING_FIELD.get(name)
        if codigo is None:
            return getattr(self._base, name)
        valor = self._provider.value(codigo)
        if isinstance(valor, list) and isinstance(getattr(self._base, name, None), tuple):
            return tuple(valor)
        return valor


class CatalogParametersService:
    def __init__(
        self,
        repository: SQLiteCatalogParameterRepository,
        audit_repository: SQLiteAuditRepository,
        cache: CatalogParametersCache,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.audit_repository = audit_repository
        self.cache = cache
        self.settings = settings
        self.settings_view = CatalogSettingsView(self, settings)
        self._seed_lock = Lock()

    # ------------------------------------------------------------- accesos
    def _ensure_ready(self) -> CatalogParameterVersion:
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
                modulo=CATALOG_MODULO,
            )

    def snapshot(self) -> CatalogParameterSnapshot:
        """Instantánea vigente; la caché solo sirve si coincide la versión."""

        version = self._ensure_ready()
        cached = self.cache.get(version.version)
        if cached is not None:
            return cached
        snapshot = version.snapshot()
        self.cache.set(snapshot)
        return snapshot

    def value(self, codigo: str) -> Any:
        """Punto de lectura usado por las funciones consumidoras."""

        return self.snapshot().value(codigo)

    def current(self) -> CatalogParameterVersion:
        return self.repository.latest() or self._ensure_ready()

    def history(self, *, limit: int = 50) -> list[CatalogParameterVersion]:
        self._ensure_ready()
        return self.repository.list_versions(limit=limit)

    def get_version(self, version: int) -> CatalogParameterVersion:
        self._ensure_ready()
        found = self.repository.get(version)
        if found is None:
            raise CatalogParameterVersionNotFoundError(
                f"No existe la versión {version} de los parámetros del catálogo.",
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
        # El rol administrador o el alcance explícito habilitan la operación.
        # Un alcance de otro módulo (p. ej. catalog.category.write) no basta.
        if ADMIN_ROLE not in roles and CATALOG_PARAMETERS_WRITE_SCOPE not in roles:
            raise CatalogParametersForbiddenError(
                "Se requiere el permiso admin.catalog.parameters.write para administrar parámetros.",
                details={"actorId": actor.id, "roles": list(actor.roles)},
            )

    # ---------------------------------------------------------- validación
    @staticmethod
    def _validar_modulo(modulo: str) -> None:
        if modulo != CATALOG_MODULO:
            raise CatalogParameterModuleError(
                "El módulo indicado no corresponde al catálogo.",
                details={"modulo": modulo, "moduloPermitido": CATALOG_MODULO},
            )

    @staticmethod
    def _definicion(codigo: str) -> Any:
        definicion = DEFINICIONES_POR_CODIGO.get(codigo)
        if definicion is not None:
            return definicion
        for prefijo, modulo in MODULOS_AJENOS.items():
            if codigo.startswith(prefijo):
                raise CatalogParameterModuleError(
                    f"El parámetro {codigo} pertenece al módulo {modulo}.",
                    details={
                        "codigo": codigo,
                        "modulo": modulo,
                        "moduloPermitido": CATALOG_MODULO,
                    },
                )
        raise CatalogParameterNotFoundError(
            f"El parámetro {codigo} no existe en el catálogo de parámetros.",
            details={"codigo": codigo, "modulo": CATALOG_MODULO},
        )

    def _validar_cambios(
        self, parametros: dict[str, Any], actual: CatalogParameterVersion
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not parametros:
            raise InvalidCatalogParameterError(
                "Se requiere al menos un parámetro para actualizar.",
                details={"motivo": "sin_parametros", "versionActual": actual.version},
            )

        errores: list[dict[str, Any]] = []
        nuevos: dict[str, Any] = {}
        for codigo, valor in parametros.items():
            definicion = self._definicion(codigo)
            try:
                nuevos[codigo] = definicion.validar_valor(valor)
            except InvalidCatalogParameterError as exc:
                errores.extend(exc.details.get("errores", []))
        if errores:
            raise InvalidCatalogParameterError(
                "Los valores propuestos no son válidos.",
                details={"errores": errores, "versionActual": actual.version},
            )

        fusionados = dict(actual.valores)
        fusionados.update(nuevos)
        try:
            validar_dependencias(fusionados)
        except InvalidCatalogParameterError as exc:
            raise InvalidCatalogParameterError(
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
        modulo: str = CATALOG_MODULO,
        motivo: str | None = None,
    ) -> CatalogParameterVersion:
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
            modulo=CATALOG_MODULO,
        )
        self.audit_repository.record(
            AuditEvent(
                entidad=CATALOG_PARAMETERS_ENTITY,
                entidad_id=f"catalog:version-{version.version}",
                accion="parametros_actualizados",
                actor_id=actor.id,
                actor_roles=actor.roles,
                fecha=fecha,
                cambios={
                    "version": version.version,
                    "versionAnterior": actual.version,
                    "modulo": CATALOG_MODULO,
                    "motivo": version.motivo,
                    "anteriores": anteriores,
                    "valores": nuevos,
                },
            )
        )
        self.cache.invalidate()
        return version
