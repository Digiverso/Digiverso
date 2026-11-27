"""Caso de uso FUN-53 / PRC-53: parametrización de comercio.

Orquesta validación, reglas de negocio, versionamiento inmutable, auditoría e
invalidación de la caché por versión. Los consumidores leen los valores
vigentes a través de ``settings_view``: cada acceso a un campo COM resuelve la
versión actual, por lo que un cambio se aplica en la siguiente petición sin
recrear servicios.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.cache.commerce_parameters import CommerceParametersCache
from app.core.config import Settings
from app.domain.actor import ADMIN_ROLE, Actor
from app.domain.audit import AuditEvent
from app.domain.commerce_parameters import (
    CODIGO_BY_SETTING_FIELD,
    COMMERCE_MODULO,
    COMMERCE_PARAMETERS_ENTITY,
    COMMERCE_PARAMETERS_WRITE_SCOPE,
    DEFINICIONES_POR_CODIGO,
    MODULOS_AJENOS,
    CommerceParameterSnapshot,
    CommerceParameterVersion,
    validar_reglas_negocio,
    valores_iniciales,
)
from app.domain.commerce_parameter_exceptions import (
    CommerceParameterModuleError,
    CommerceParameterNotFoundError,
    CommerceParameterVersionNotFoundError,
    CommerceParametersForbiddenError,
    InvalidCommerceParameterError,
)
from app.repository.audit import SQLiteAuditRepository
from app.repository.commerce_parameters import SQLiteCommerceParameterRepository


class CommerceSettingsView:
    """Vista de ``Settings`` que relee la versión vigente en cada acceso.

    Los campos que no pertenecen a comercio se delegan al objeto original. De
    este modo la vista puede encadenarse con la de catálogo sin perder ningún
    parámetro de los otros módulos.
    """

    def __init__(self, provider: "CommerceParametersService", base: Settings) -> None:
        object.__setattr__(self, "_provider", provider)
        object.__setattr__(self, "_base", base)

    def __getattr__(self, name: str) -> Any:
        codigo = CODIGO_BY_SETTING_FIELD.get(name)
        if codigo is None:
            return getattr(self._base, name)
        return self._provider.value(codigo)


class CommerceParametersService:
    def __init__(
        self,
        repository: SQLiteCommerceParameterRepository,
        audit_repository: SQLiteAuditRepository,
        cache: CommerceParametersCache,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.audit_repository = audit_repository
        self.cache = cache
        self.settings = settings
        self.settings_view = CommerceSettingsView(self, settings)
        self._seed_lock = Lock()

    # ------------------------------------------------------------- accesos
    def _ensure_ready(self) -> CommerceParameterVersion:
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
                modulo=COMMERCE_MODULO,
            )

    def snapshot(self) -> CommerceParameterSnapshot:
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

    def current(self) -> CommerceParameterVersion:
        return self.repository.latest() or self._ensure_ready()

    def history(self, *, limit: int = 50) -> list[CommerceParameterVersion]:
        self._ensure_ready()
        return self.repository.list_versions(limit=limit)

    def get_version(self, version: int) -> CommerceParameterVersion:
        self._ensure_ready()
        found = self.repository.get(version)
        if found is None:
            raise CommerceParameterVersionNotFoundError(
                f"No existe la versión {version} de los parámetros de comercio.",
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
        # Un alcance de otro módulo (p. ej. admin.catalog.parameters.write)
        # no basta.
        if ADMIN_ROLE not in roles and COMMERCE_PARAMETERS_WRITE_SCOPE not in roles:
            raise CommerceParametersForbiddenError(
                "Se requiere el permiso admin.commerce.parameters.write para administrar parámetros.",
                details={"actorId": actor.id, "roles": list(actor.roles)},
            )

    # ---------------------------------------------------------- validación
    @staticmethod
    def _validar_modulo(modulo: str) -> None:
        if modulo != COMMERCE_MODULO:
            raise CommerceParameterModuleError(
                "El módulo indicado no corresponde a comercio.",
                details={"modulo": modulo, "moduloPermitido": COMMERCE_MODULO},
            )

    @staticmethod
    def _definicion(codigo: str) -> Any:
        definicion = DEFINICIONES_POR_CODIGO.get(codigo)
        if definicion is not None:
            return definicion
        for prefijo, modulo in MODULOS_AJENOS.items():
            if codigo.startswith(prefijo):
                raise CommerceParameterModuleError(
                    f"El parámetro {codigo} pertenece al módulo {modulo}.",
                    details={
                        "codigo": codigo,
                        "modulo": modulo,
                        "moduloPermitido": COMMERCE_MODULO,
                    },
                )
        raise CommerceParameterNotFoundError(
            f"El parámetro {codigo} no existe en el catálogo de parámetros.",
            details={"codigo": codigo, "modulo": COMMERCE_MODULO},
        )

    def _validar_cambios(
        self, parametros: dict[str, Any], actual: CommerceParameterVersion
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not parametros:
            raise InvalidCommerceParameterError(
                "Se requiere al menos un parámetro para actualizar.",
                details={"motivo": "sin_parametros", "versionActual": actual.version},
            )

        errores: list[dict[str, Any]] = []
        nuevos: dict[str, Any] = {}
        for codigo, valor in parametros.items():
            definicion = self._definicion(codigo)
            try:
                nuevos[codigo] = definicion.validar_valor(valor)
            except InvalidCommerceParameterError as exc:
                errores.extend(exc.details.get("errores", []))
        if errores:
            raise InvalidCommerceParameterError(
                "Los valores propuestos no son válidos.",
                details={"errores": errores, "versionActual": actual.version},
            )

        fusionados = dict(actual.valores)
        fusionados.update(nuevos)
        try:
            validar_reglas_negocio(fusionados)
        except InvalidCommerceParameterError as exc:
            raise InvalidCommerceParameterError(
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
        modulo: str = COMMERCE_MODULO,
        motivo: str | None = None,
    ) -> CommerceParameterVersion:
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
            modulo=COMMERCE_MODULO,
        )
        self.audit_repository.record(
            AuditEvent(
                entidad=COMMERCE_PARAMETERS_ENTITY,
                entidad_id=f"commerce:version-{version.version}",
                accion="parametros_actualizados",
                actor_id=actor.id,
                actor_roles=actor.roles,
                fecha=fecha,
                cambios={
                    "version": version.version,
                    "versionAnterior": actual.version,
                    "modulo": COMMERCE_MODULO,
                    "motivo": version.motivo,
                    "anteriores": anteriores,
                    "valores": nuevos,
                },
            )
        )
        self.cache.invalidate()
        return version
