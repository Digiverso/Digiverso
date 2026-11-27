"""Caso de uso FUN-64 / PRC-64: parametrización de comunidad.

Orquesta validación, versionamiento inmutable, auditoría e invalidación de
caché. Los cambios se propagan a los objetos de configuración que ya consumen
las funciones de comunidad (reseñas, seguimiento, feed, recomendaciones y
notificaciones), sin importar en qué rama se hayan creado esos servicios.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.cache.community_parameters import CommunityParametersCache
from app.core.config import Settings
from app.domain.actor import ADMIN_ROLE, Actor
from app.domain.audit import AuditEvent
from app.domain.community_parameters import (
    CODIGO_BY_ALIAS,
    CODIGO_BY_SETTING_FIELD,
    COMMUNITY_MODULO,
    COMMUNITY_PARAMETERS_ENTITY,
    COMMUNITY_PARAMETERS_WRITE_SCOPE,
    DEFINICIONES_POR_CODIGO,
    MODULOS_AJENOS,
    PARAMETROS_COMUNIDAD,
    CommunityParameterSnapshot,
    CommunityParameterVersion,
    validar_dependencias,
    valores_iniciales,
)
from app.domain.community_parameter_exceptions import (
    CommunityParameterModuleError,
    CommunityParameterNotFoundError,
    CommunityParameterVersionNotFoundError,
    CommunityParametersForbiddenError,
    InvalidCommunityParameterError,
)
from app.repository.audit import SQLiteAuditRepository
from app.repository.community_parameters import SQLiteCommunityParameterRepository


class CommunitySettingsView:
    """Vista de ``Settings`` que relee la versión vigente en cada acceso.

    Expone tanto los campos ``community_*`` como los nombres usados por los
    ``CommunitySettings`` de HU-19 (``max_following``, ``max_page_size``, ...).
    Los campos ajenos a comunidad se delegan al objeto original.
    """

    def __init__(self, provider: "CommunityParametersService", base: Settings) -> None:
        object.__setattr__(self, "_provider", provider)
        object.__setattr__(self, "_base", base)

    def __getattr__(self, name: str) -> Any:
        codigo = CODIGO_BY_SETTING_FIELD.get(name) or CODIGO_BY_ALIAS.get(name)
        if codigo is not None:
            return self._provider.value(codigo)
        return getattr(self._base, name)


class CommunityParametersService:
    def __init__(
        self,
        repository: SQLiteCommunityParameterRepository,
        audit_repository: SQLiteAuditRepository,
        cache: CommunityParametersCache,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.audit_repository = audit_repository
        self.cache = cache
        self.settings = settings
        self.settings_view = CommunitySettingsView(self, settings)
        self._consumers: list[Any] = []
        self._related_caches: list[Any] = []
        self._seed_lock = Lock()

    # ------------------------------------------------------------- accesos
    def _ensure_ready(self) -> CommunityParameterVersion:
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
                modulo=COMMUNITY_MODULO,
            )

    def snapshot(self) -> CommunityParameterSnapshot:
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

    def current(self) -> CommunityParameterVersion:
        return self.repository.latest() or self._ensure_ready()

    def history(self, *, limit: int = 50) -> list[CommunityParameterVersion]:
        self._ensure_ready()
        return self.repository.list_versions(limit=limit)

    def get_version(self, version: int) -> CommunityParameterVersion:
        self._ensure_ready()
        encontrada = self.repository.get(version)
        if encontrada is None:
            raise CommunityParameterVersionNotFoundError(
                f"No existe la versión {version} de los parámetros de comunidad.",
                details={"version": version},
            )
        return encontrada

    # ----------------------------------------------------------- permisos
    @classmethod
    def ensure_admin(cls, actor: Actor) -> None:
        """Guard público para consultas y escrituras administrativas."""

        cls._ensure_admin(actor)

    @staticmethod
    def _ensure_admin(actor: Actor) -> None:
        roles = set(actor.roles)
        if ADMIN_ROLE not in roles and COMMUNITY_PARAMETERS_WRITE_SCOPE not in roles:
            raise CommunityParametersForbiddenError(
                "Se requiere el permiso admin.community.parameters.write "
                "para administrar parámetros.",
                details={"actorId": actor.id, "roles": list(actor.roles)},
            )

    # ---------------------------------------------------------- validación
    @staticmethod
    def _validar_modulo(modulo: str) -> None:
        if modulo != COMMUNITY_MODULO:
            raise CommunityParameterModuleError(
                "El módulo indicado no corresponde a la comunidad.",
                details={"modulo": modulo, "moduloPermitido": COMMUNITY_MODULO},
            )

    @staticmethod
    def _definicion(codigo: str) -> Any:
        definicion = DEFINICIONES_POR_CODIGO.get(codigo)
        if definicion is not None:
            return definicion
        for prefijo, modulo in MODULOS_AJENOS.items():
            if codigo.startswith(prefijo):
                raise CommunityParameterModuleError(
                    f"El parámetro {codigo} pertenece al módulo {modulo}.",
                    details={
                        "codigo": codigo,
                        "modulo": modulo,
                        "moduloPermitido": COMMUNITY_MODULO,
                    },
                )
        raise CommunityParameterNotFoundError(
            f"El parámetro {codigo} no existe en el catálogo de parámetros.",
            details={"codigo": codigo, "modulo": COMMUNITY_MODULO},
        )

    def _validar_cambios(
        self, parametros: dict[str, Any], actual: CommunityParameterVersion
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not parametros:
            raise InvalidCommunityParameterError(
                "Se requiere al menos un parámetro para actualizar.",
                details={"motivo": "sin_parametros", "versionActual": actual.version},
            )

        errores: list[dict[str, Any]] = []
        nuevos: dict[str, Any] = {}
        for codigo, valor in parametros.items():
            definicion = self._definicion(codigo)
            try:
                nuevos[codigo] = definicion.validar_valor(valor)
            except InvalidCommunityParameterError as exc:
                errores.extend(exc.details.get("errores", []))
        if errores:
            raise InvalidCommunityParameterError(
                "Los valores propuestos no son válidos.",
                details={"errores": errores, "versionActual": actual.version},
            )

        fusionados = dict(actual.valores)
        fusionados.update(nuevos)
        try:
            validar_dependencias(fusionados)
        except InvalidCommunityParameterError as exc:
            raise InvalidCommunityParameterError(
                exc.message,
                details={**exc.details, "versionActual": actual.version},
            ) from exc

        anteriores = {codigo: actual.valores[codigo] for codigo in nuevos}
        return nuevos, anteriores

    # --------------------------------------------------------- consumidores
    def register_consumer(self, consumer: Any) -> None:
        """Registra un objeto de configuración que lee parámetros COMU."""

        if consumer is None or any(consumer is item for item in self._consumers):
            return
        self._consumers.append(consumer)

    def register_cache(self, cache: Any) -> None:
        """Registra una caché de otra HU que debe limpiarse tras un cambio."""

        if cache is None or any(cache is item for item in self._related_caches):
            return
        self._related_caches.append(cache)

    def _apply_to_consumers(self, valores: dict[str, Any]) -> None:
        for consumer in self._consumers:
            for codigo, valor in valores.items():
                definicion = DEFINICIONES_POR_CODIGO[codigo]
                atributos = (definicion.setting_field, *definicion.aliases)
                for atributo in atributos:
                    try:
                        # Las vistas de ``Settings`` delegan los campos que no
                        # conocen, así que no basta con ``hasattr``: se asigna
                        # directamente. Los objetos son frozen dataclasses; se
                        # respeta su tipo para no romper ``dataclasses.replace``.
                        object.__setattr__(consumer, atributo, valor)
                    except Exception:  # pragma: no cover - objetos read-only
                        continue

    def _invalidate(self) -> None:
        self.cache.invalidate()
        for cache in self._related_caches:
            try:
                cache.invalidate()
            except TypeError:
                clear = getattr(cache, "clear", None)
                if callable(clear):
                    clear()

    # ------------------------------------------------------------ escritura
    def update(
        self,
        actor: Actor,
        *,
        parametros: dict[str, Any],
        modulo: str = COMMUNITY_MODULO,
        motivo: str | None = None,
    ) -> CommunityParameterVersion:
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
            modulo=COMMUNITY_MODULO,
        )
        self.audit_repository.record(
            AuditEvent(
                entidad=COMMUNITY_PARAMETERS_ENTITY,
                entidad_id=f"community:version-{version.version}",
                accion="parametros_actualizados",
                actor_id=actor.id,
                actor_roles=actor.roles,
                fecha=fecha,
                cambios={
                    "version": version.version,
                    "versionAnterior": actual.version,
                    "modulo": COMMUNITY_MODULO,
                    "motivo": version.motivo,
                    "anteriores": anteriores,
                    "valores": nuevos,
                },
            )
        )
        self._apply_to_consumers(nuevos)
        self._invalidate()
        return version


def bind_community_consumers(application: Any, service: CommunityParametersService) -> None:
    """Conecta la parametrización con los consumidores presentes en la app.

    Se invoca al final del ciclo de vida del factory: si una rama de comunidad
    está fusionada, sus servicios y cachés ya existen en ``app.state``. Si no
    están, no hay nada que enlazar y el arranque sigue funcionando igual.
    """

    candidatos: list[Any] = [
        getattr(application.state, "settings", None),
        getattr(application.state, "community_settings", None),
    ]
    for clave in (
        "community_service",
        "review_service",
        "community_notification_service",
        "community_notifications_service",
    ):
        objeto = getattr(application.state, clave, None)
        candidatos.append(getattr(objeto, "settings", None))

    for candidato in candidatos:
        service.register_consumer(candidato)

    for clave in ("community_feed_cache", "rating_cache"):
        service.register_cache(getattr(application.state, clave, None))
