"""Configuración compartida de la API (autenticación + catálogo)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

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


def _read_env_file() -> dict[str, str]:
    path = Path(__file__).resolve().parents[2] / ".env"
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        cleaned = value.strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
            cleaned = cleaned[1:-1]
        values[key.strip()] = cleaned
    return values


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip().lower() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    """Parámetros de ejecución de todos los módulos implementados.

    Los campos ``category_name_*`` materializan la regla CAT-17, cuyo valor
    numérico no estaba definido en el repositorio.
    """

    # Aplicación
    app_name: str = "Digiverso API"
    app_env: str = "development"
    app_debug: bool = True
    app_port: int = 8000

    # Autenticación (HU-01)
    secret_key: str = "cambia-este-valor-en-produccion"
    password_min_length: int = 8
    password_require_uppercase: bool = True
    password_require_lowercase: bool = True
    password_require_digit: bool = True
    password_require_special: bool = True
    verification_token_ttl_minutes: int = 15
    verification_url_base: str = "http://127.0.0.1:8000/verificar-correo"
    register_rate_limit: int = 10
    rate_limit_window_seconds: int = 600
    email_provider: str = "console"
    email_from: str = "no-responder@digiverso.local"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True

    # Sesión y recuperación (HU-02)
    jwt_private_key: str = ""
    jwt_public_key: str = ""
    jwt_issuer: str = "digiverso"
    jwt_audience: str = "digiverso-api"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    password_reset_ttl_minutes: int = 30
    password_reset_url_base: str = "http://127.0.0.1:8000/restablecer-contrasena"
    max_failed_login_attempts: int = 5
    account_lock_minutes: int = 15
    login_rate_limit: int = 10
    password_recovery_rate_limit: int = 5

    # Catálogo (HU-07)
    database_path: Path = field(
        default_factory=lambda: sqlite_path(
            os.getenv("DATABASE_URL", "sqlite:///./dev.db")
        )
    )
    category_name_min_length: int = 2
    category_name_max_length: int = 80
    category_description_max_length: int = 500
    require_explicit_actor: bool = False
    default_actor_id: str = "usr_admin"

    # Catálogo (HU-08). Los valores numéricos de CAT-03/09/11/12/13 no estaban
    # definidos en el repositorio; se fijan aquí y son sobreescribibles por .env.
    product_min_price: int = 3500  # CAT-01
    product_currency: str = "COP"
    product_max_age: int = 99  # CAT-03
    product_min_images: int = 1  # CAT-09
    product_name_min_length: int = 2  # CAT-11
    product_name_max_length: int = 120  # CAT-11
    product_description_min_length: int = 1  # CAT-12
    product_description_max_length: int = 2000  # CAT-12
    product_max_categories: int = 5  # CAT-13
    # Catálogo · búsqueda y vitrina (HU-10)
    catalog_default_page_size: int = 20
    catalog_max_page_size: int = 100
    actor_token_ttl_seconds: int = 3600

    # Catálogo (HU-09). CAT-05/06/07/08/10 no tenían valores numéricos en el
    # repositorio: se fijan aquí y se sobreescriben desde .env.
    media_image_formats: tuple[str, ...] = ("jpg", "png", "webp")  # CAT-05
    media_video_formats: tuple[str, ...] = ("mp4", "mov", "webm")  # CAT-07
    media_max_image_bytes: int = 10 * 1024 * 1024  # CAT-06
    media_max_video_bytes: int = 200 * 1024 * 1024  # CAT-08
    media_max_per_product: int = 10  # CAT-10
    media_storage_dir: Path = Path("uploads/media")
    media_url_base: str = "https://cdn.digiverso.com/products"

    @property
    def media_max_read_bytes(self) -> int:
        """Tope de lectura del cuerpo: basta para detectar CAT-06/CAT-08."""

        return max(self.media_max_image_bytes, self.media_max_video_bytes) + 1

    @property
    def debug(self) -> bool:
        """Alias de ``app_debug`` usado por el factory de aplicación."""

        return self.app_debug


def load_settings() -> Settings:
    file_values = _read_env_file()

    def value(name: str, default: str) -> str:
        return os.getenv(name, file_values.get(name, default))

    return Settings(
        app_name=value("APP_NAME", "Digiverso API"),
        app_env=value("APP_ENV", "development"),
        app_debug=_as_bool(value("APP_DEBUG", "true")),
        app_port=int(value("APP_PORT", "8000")),
        secret_key=value("SECRET_KEY", "cambia-este-valor-en-produccion"),
        password_min_length=int(value("AUTH_PASSWORD_MIN_LENGTH", "8")),
        password_require_uppercase=_as_bool(
            value("AUTH_PASSWORD_REQUIRE_UPPERCASE", "true")
        ),
        password_require_lowercase=_as_bool(
            value("AUTH_PASSWORD_REQUIRE_LOWERCASE", "true")
        ),
        password_require_digit=_as_bool(value("AUTH_PASSWORD_REQUIRE_DIGIT", "true")),
        password_require_special=_as_bool(
            value("AUTH_PASSWORD_REQUIRE_SPECIAL", "true")
        ),
        verification_token_ttl_minutes=int(
            value("AUTH_VERIFICATION_TOKEN_TTL_MINUTES", "15")
        ),
        verification_url_base=value(
            "AUTH_VERIFICATION_URL_BASE",
            "http://127.0.0.1:8000/verificar-correo",
        ),
        register_rate_limit=int(value("AUTH_REGISTER_RATE_LIMIT", "10")),
        rate_limit_window_seconds=int(
            value("AUTH_RATE_LIMIT_WINDOW_SECONDS", "600")
        ),
        email_provider=value("EMAIL_PROVIDER", "console").strip().lower(),
        email_from=value("EMAIL_FROM", "no-responder@digiverso.local"),
        smtp_host=value("SMTP_HOST", ""),
        smtp_port=int(value("SMTP_PORT", "587")),
        smtp_username=value("SMTP_USERNAME", ""),
        smtp_password=value("SMTP_PASSWORD", ""),
        smtp_use_tls=_as_bool(value("SMTP_USE_TLS", "true")),
        jwt_private_key=value("AUTH_JWT_PRIVATE_KEY", ""),
        jwt_public_key=value("AUTH_JWT_PUBLIC_KEY", ""),
        jwt_issuer=value("AUTH_JWT_ISSUER", "digiverso"),
        jwt_audience=value("AUTH_JWT_AUDIENCE", "digiverso-api"),
        access_token_ttl_minutes=int(value("AUTH_ACCESS_TOKEN_TTL_MINUTES", "15")),
        refresh_token_ttl_days=int(value("AUTH_REFRESH_TOKEN_TTL_DAYS", "7")),
        password_reset_ttl_minutes=int(value("AUTH_PASSWORD_RESET_TTL_MINUTES", "30")),
        password_reset_url_base=value(
            "AUTH_PASSWORD_RESET_URL_BASE",
            "http://127.0.0.1:8000/restablecer-contrasena",
        ),
        max_failed_login_attempts=int(value("AUTH_MAX_FAILED_LOGIN_ATTEMPTS", "5")),
        account_lock_minutes=int(value("AUTH_ACCOUNT_LOCK_MINUTES", "15")),
        login_rate_limit=int(value("AUTH_LOGIN_RATE_LIMIT", "10")),
        password_recovery_rate_limit=int(value("AUTH_PASSWORD_RECOVERY_RATE_LIMIT", "5")),
        database_path=sqlite_path(value("DATABASE_URL", "sqlite:///./dev.db")),
        category_name_min_length=int(value("CAT_17_MIN_LENGTH", "2")),
        category_name_max_length=int(value("CAT_17_MAX_LENGTH", "80")),
        category_description_max_length=int(value("CAT_17_DESCRIPTION_MAX", "500")),
        require_explicit_actor=_as_bool(value("REQUIRE_EXPLICIT_ACTOR", "false")),
        default_actor_id=value("DEFAULT_ADMIN_ACTOR_ID", "usr_admin"),
        product_min_price=int(value("CAT_01_MIN_PRICE", "3500")),
        product_currency=value("CAT_01_CURRENCY", "COP").strip().upper(),
        product_max_age=int(value("CAT_03_MAX_AGE", "99")),
        product_min_images=int(value("CAT_09_MIN_IMAGES", "1")),
        product_name_min_length=int(value("CAT_11_MIN_LENGTH", "2")),
        product_name_max_length=int(value("CAT_11_MAX_LENGTH", "120")),
        product_description_min_length=int(value("CAT_12_MIN_LENGTH", "1")),
        product_description_max_length=int(value("CAT_12_MAX_LENGTH", "2000")),
        product_max_categories=int(value("CAT_13_MAX_CATEGORIES", "5")),
        catalog_default_page_size=int(value("CATALOG_DEFAULT_PAGE_SIZE", "20")),
        catalog_max_page_size=int(value("CATALOG_MAX_PAGE_SIZE", "100")),
        actor_token_ttl_seconds=int(value("ACTOR_TOKEN_TTL_SECONDS", "3600")),
        media_image_formats=_as_tuple(value("CAT_05_IMAGE_FORMATS", "jpg,png,webp")),
        media_video_formats=_as_tuple(value("CAT_07_VIDEO_FORMATS", "mp4,mov,webm")),
        media_max_image_bytes=int(value("CAT_06_MAX_IMAGE_BYTES", str(10 * 1024 * 1024))),
        media_max_video_bytes=int(value("CAT_08_MAX_VIDEO_BYTES", str(200 * 1024 * 1024))),
        media_max_per_product=int(value("CAT_10_MAX_MEDIA", "10")),
        media_storage_dir=Path(value("MEDIA_STORAGE_DIR", "uploads/media")).expanduser(),
        media_url_base=value(
            "MEDIA_URL_BASE", "https://cdn.digiverso.com/products"
        ).rstrip("/"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Configuración cacheada usada por el factory de aplicación."""

    return load_settings()


settings = load_settings()
