from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict



TRUSTED_VENDOR_DOMAINS = (
    "amazon.in",
    "flipkart.com",
    "myntra.com",
    "ajio.com",
    "tatacliq.com",
    "croma.com",
    "reliancedigital.in",
    "vijaysales.com",
    "jiomart.com",
    "bigbasket.com",
    "nykaa.com",
    "firstcry.com",
    "snapdeal.com",
    "shopclues.com",
    "samsung.com",
    "mi.com",
    "oneplus.in",
    "apple.com",
    "myimaginestore.com",
    "cashify.in",
    "pepperfry.com",
    "dell.com",
    "hp.com",
    "lenovo.com",
    "asus.com",
    "acer.com",
    "msi.com",
    "lg.com",
    "sony.co.in",
    "panasonic.com",
    "vivo.com",
    "oppo.com",
    "realme.com",
    "motorola.in",
    "nothing.tech",
    "poorvika.com",
    "honor.com",
    "infinixmobiles.in",
    "tecno-mobile.in",
    "tcl.com",
    "hisense-india.com",
    "boat-lifestyle.com",
    "moglix.com",
    "robu.in",
    "ibo.com",
    "globalelectronics.in",
    "electronicscomp.com",
)

DEFAULT_DEV_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
    "http://localhost:5176",
    "http://127.0.0.1:5176",
    "http://localhost:5177",
    "http://127.0.0.1:5177",
    "http://localhost:5178",
    "http://127.0.0.1:5178",
    "http://localhost:5179",
    "http://127.0.0.1:5179",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:4174",
    "http://127.0.0.1:4174",
    "http://localhost:4175",
    "http://127.0.0.1:4175",
    "http://localhost:4176",
    "http://127.0.0.1:4176",
)


class Settings(BaseSettings):
    app_name: str = "Costiqo API"
    api_v1_prefix: str = "/api/v1"
    environment: str = "development"
    secret_key: str = "change-me-before-production"
    access_token_expire_minutes: int = 60 * 24
    database_url: str = "sqlite:///./costiqo.db"
    neon_database_url: str | None = None
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_recycle_seconds: int = 1800
    auto_create_schema: bool = True
    enabled_sources_raw: str = (
        "amazon,flipkart,poorvika,reliance-digital,"
        "croma,moglix,robu,electronicscomp,ibo,global-electronics"
    )
    degraded_sources_raw: str = ""
    primary_sources_raw: str = ""
    background_sources_raw: str = ""
    trusted_vendor_domains_raw: str = ",".join(TRUSTED_VENDOR_DOMAINS)
    openrouter_key: str | None = None
    openrouter_model: str = "google/gemini-2.5-flash"
    llm_validation_enabled: bool = True
    llm_validation_timeout_seconds: float = 3
    llm_validation_max_candidates: int = 12
    llm_validation_batch_size: int = 4
    llm_validation_parallel_batches: int = 3
    scrape_cache_ttl_seconds: int = 900
    background_scrape_cache_ttl_seconds: int = 3600
    scrape_retry_attempts: int = 2
    scrape_retry_backoff_seconds: float = 1.0
    offer_verification_enabled: bool = True
    offer_verification_timeout_seconds: int = 8
    offer_verification_cache_ttl_seconds: int = 900
    offer_verification_max_offers: int = 2
    queue_backend: str = "inline"
    queue_name: str = "costiqo-scrape"
    queue_job_timeout_seconds: int = 900
    queue_result_ttl_seconds: int = 60
    queue_lock_ttl_seconds: int = 180
    redis_url: str = "redis://localhost:6379/0"
    cors_origins_raw: str = ",".join(DEFAULT_DEV_CORS_ORIGINS)
    scheduled_refresh_limit: int = 25
    scheduled_refresh_location: str | None = None
    scheduled_refresh_pincode: str | None = None
    bootstrap_vendors_on_startup: bool = True
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 240
    rate_limit_window_seconds: int = 60

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_security_configuration(self) -> "Settings":
        env = self.environment.strip().lower()
        if env not in {"development", "test"}:
            insecure_defaults = {
                "change-me-before-production",
                "secret",
                "changeme",
                "jwt-secret",
                "default",
            }
            if (
                not self.secret_key
                or self.secret_key in insecure_defaults
                or len(self.secret_key) < 32
            ):
                raise ValueError(
                    f"Insecure secret_key configuration for environment '{self.environment}'. "
                    "A strong secret with a minimum length of 32 characters must be configured outside development."
                )
        return self


    @property
    def active_database_url(self) -> str:
        if self.environment.lower() == "test":
            return self.database_url
        return self.neon_database_url or self.database_url

    @property
    def is_sqlite(self) -> bool:
        return self.active_database_url.startswith("sqlite")

    @property
    def effective_rate_limit_enabled(self) -> bool:
        return self.rate_limit_enabled and self.environment.lower() != "test"

    @property
    def enabled_sources(self) -> list[str]:
        return [
            source.strip().lower()
            for source in self.enabled_sources_raw.split(",")
            if source.strip()
        ]

    @property
    def primary_sources(self) -> list[str]:
        if self.primary_sources_raw.strip():
            return self._parse_sources(self.primary_sources_raw)
        return self.enabled_sources

    @property
    def degraded_sources(self) -> list[str]:
        return self._parse_sources(self.degraded_sources_raw)

    @property
    def background_sources(self) -> list[str]:
        if self.background_sources_raw.strip():
            return self._parse_sources(self.background_sources_raw)
        return []

    @property
    def all_configured_sources(self) -> list[str]:
        ordered: list[str] = []
        for source_name in [*self.enabled_sources, *self.primary_sources, *self.background_sources]:
            if source_name not in ordered:
                ordered.append(source_name)
        return ordered

    @property
    def trusted_vendor_domains(self) -> tuple[str, ...]:
        return tuple(self._split_csv(self.trusted_vendor_domains_raw))

    @property
    def cors_origins(self) -> list[str]:
        configured = self._split_csv(self.cors_origins_raw)
        origins: list[str] = []
        for origin in [*DEFAULT_DEV_CORS_ORIGINS, *configured]:
            if origin not in origins:
                origins.append(origin)
        return origins

    def _parse_sources(self, raw_sources: str) -> list[str]:
        return [source.lower() for source in self._split_csv(raw_sources)]

    def _split_csv(self, raw_value: str) -> list[str]:
        return [
            item.strip()
            for item in raw_value.split(",")
            if item.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
