"""Configuración de la aplicación para el módulo de catálogo."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SQLITE_PREFIX = "sqlite:///"


def sqlite_path(database_url: str) -> Path:
    """Convierte una URL ``sqlite:///ruta`` en una ruta absoluta de sistema."""

    if not database_url.startswith(SQLITE_PREFIX):
        raise ValueError(
            "DATABASE_URL no soportada; se espera el formato sqlite:///ruta/al/archivo.db"
        )
    raw_path = database_url[len(SQLITE_PREFIX) :]
    path = Path(raw_path).expanduser()
    return path if path.is_absolute() else Path.cwd() / path


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Parámetros de ejecución.

    Los límites ``category_name_*`` materializan la regla CAT-17, cuyo valor
    numérico no estaba definido en el repositorio. El valor por defecto es
    configurable mediante variables de entorno.
    """

    app_name: str = "Digiverso API"
    app_env: str = "development"
    debug: bool = True
    database_path: Path = field(
        default_factory=lambda: sqlite_path(
            os.getenv("DATABASE_URL", "sqlite:///./dev.db")
        )
    )
    category_name_min_length: int = int(os.getenv("CAT_17_MIN_LENGTH", "2"))
    category_name_max_length: int = int(os.getenv("CAT_17_MAX_LENGTH", "80"))
    category_description_max_length: int = int(os.getenv("CAT_17_DESCRIPTION_MAX", "500"))
    require_explicit_actor: bool = _env_bool("REQUIRE_EXPLICIT_ACTOR", False)
    default_actor_id: str = os.getenv("DEFAULT_ADMIN_ACTOR_ID", "usr_admin")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve la configuración compartida del proceso."""

    return Settings()
