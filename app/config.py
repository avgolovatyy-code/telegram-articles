"""Application configuration.

Every tunable value lives here so that business logic never hardcodes model names,
budgets, channels or affiliate identifiers.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Market = Literal["en", "ru"]
MARKETS: tuple[Market, ...] = ("en", "ru")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- runtime
    app_env: str = "local"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"
    timezone: str = "UTC"
    admin_base_url: str = "http://localhost:8000"

    # --------------------------------------------------------------- database
    database_url: str = "sqlite+pysqlite:///./var/engine.sqlite3"
    database_echo: bool = False

    # -------------------------------------------------------------- WeGoTrip
    wegotrip_api_base_url: str = "https://app.wegotrip.com/api"
    # The public documentation mentions both v2 and v3. Probing the live API shows
    # that v2 serves currencies/countries/cities/products/search while v3 only serves
    # attractions (and its `city` filter is ignored), so each endpoint pins its version.
    wegotrip_api_key: str | None = None
    wegotrip_referer_id: str = "435"
    wegotrip_timeout_seconds: float = 30.0
    wegotrip_max_retries: int = 4
    wegotrip_rate_limit_rps: float = 4.0
    wegotrip_store_domain_en: str = "wegotrip.com"
    wegotrip_store_domain_ru: str = "wegotrip.ru"
    wegotrip_currency_en: str = "EUR"
    wegotrip_currency_ru: str = "RUB"
    catalog_provider: Literal["http", "mock"] = "http"

    # -------------------------------------------------------------- Telegram
    telegram_bot_token: str | None = None
    telegram_api_base_url: str = "https://api.telegram.org"
    telegram_en_channel: str = "@wegotrip"
    telegram_ru_channel: str = "@wegotrip_ru"
    telegram_test_channel: str | None = None
    telegram_timeout_seconds: float = 60.0
    telegram_max_retries: int = 4
    telegram_dry_run: bool = False

    # ---------------------------------------------------------------- OpenAI
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_writer_model: str = "gpt-5.6-terra"
    openai_utility_model: str = "gpt-5.6-luna"
    openai_fallback_model: str = "gpt-5.6-sol"
    openai_review_model: str | None = None  # defaults to the utility model
    openai_image_model: str = "gpt-image-2"
    openai_timeout_seconds: float = 240.0
    openai_max_retries: int = 3
    llm_provider: Literal["openai", "mock"] = "openai"

    # ---------------------------------------------------------------- budget
    daily_ai_budget_usd: float = 3.00
    en_articles_min_per_day: int = 10
    en_articles_max_per_day: int = 20
    ru_articles_min_per_day: int = 10
    ru_articles_max_per_day: int = 20
    budget_safety_margin_usd: float = 0.05
    default_estimated_article_cost_usd: float = 0.09

    # ------------------------------------------------------------- publishing
    auto_publish_en: bool = False
    auto_publish_ru: bool = False
    en_publish_per_day: int = 10
    ru_publish_per_day: int = 10
    min_post_interval_minutes: int = 45
    publish_window_start_hour: int = 7
    publish_window_end_hour: int = 22
    stale_article_refresh_hours: int = 24

    # ---------------------------------------------------------------- quality
    min_quality_score: float = 0.88
    min_factuality_score: float = 0.97
    article_min_chars: int = 2500
    article_target_min_chars: int = 4000
    article_target_max_chars: int = 10000
    article_max_chars: int = 20000
    telegram_rich_message_char_limit: int = 32768
    telegram_rich_message_block_limit: int = 500
    telegram_rich_message_media_limit: int = 50
    dedup_similarity_threshold: float = 0.82

    # ------------------------------------------------------------------ media
    allow_generated_covers: bool = False
    validate_media_over_network: bool = True
    media_max_bytes: int = 10 * 1024 * 1024

    # --------------------------------------------------------------- hashtags
    enable_hashtags: bool = True
    max_hashtags: int = 4

    # -------------------------------------------------------------- analytics
    tracking_base_url: str | None = None  # defaults to admin_base_url
    utm_source: str = "telegram"
    utm_medium: str = "content"
    #: Route product buttons through /r/<token> so clicks can be counted. The redirect
    #: target always keeps coupon=<referer id> and the UTM parameters.
    use_tracking_redirect: bool = True

    # ----------------------------------------------------------------- topics
    search_demand_provider: Literal["heuristic", "none"] = "heuristic"
    topic_candidates_per_run: int = 120

    # ------------------------------------------------------------------ admin
    admin_username: str = "admin"
    admin_password: str | None = None
    scheduler_enabled: bool = True

    @field_validator("wegotrip_referer_id")
    @classmethod
    def _referer_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("WEGOTRIP_REFERER_ID must not be empty")
        return value.strip()

    @field_validator("daily_ai_budget_usd")
    @classmethod
    def _budget_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("DAILY_AI_BUDGET_USD must be > 0")
        return value

    # ------------------------------------------------------------- accessors
    @property
    def review_model(self) -> str:
        return self.openai_review_model or self.openai_utility_model

    @property
    def tracking_root(self) -> str:
        return (self.tracking_base_url or self.admin_base_url).rstrip("/")

    def store_domain(self, market: Market) -> str:
        return self.wegotrip_store_domain_ru if market == "ru" else self.wegotrip_store_domain_en

    def currency(self, market: Market) -> str:
        return self.wegotrip_currency_ru if market == "ru" else self.wegotrip_currency_en

    def telegram_channel(self, market: Market) -> str:
        return self.telegram_ru_channel if market == "ru" else self.telegram_en_channel

    def auto_publish(self, market: Market) -> bool:
        return self.auto_publish_ru if market == "ru" else self.auto_publish_en

    def articles_min_per_day(self, market: Market) -> int:
        return self.ru_articles_min_per_day if market == "ru" else self.en_articles_min_per_day

    def articles_max_per_day(self, market: Market) -> int:
        return self.ru_articles_max_per_day if market == "ru" else self.en_articles_max_per_day

    def publish_per_day(self, market: Market) -> int:
        return self.ru_publish_per_day if market == "ru" else self.en_publish_per_day

    def utm_campaign(self, market: Market) -> str:
        return f"wegotrip_{market}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """Drop the cached settings (used by tests and the CLI)."""
    get_settings.cache_clear()
    return get_settings()


settings_field_names = set(Settings.model_fields)

__all__ = [
    "MARKETS",
    "Market",
    "Settings",
    "get_settings",
    "reload_settings",
    "settings_field_names",
]
