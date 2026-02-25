"""
config.py – centralised configuration loaded from environment / .env file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    """Return env-var value or raise a descriptive error at startup."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable '{name}' is not set. "
            "Copy .env.example to .env and fill in all values."
        )
    return value


@dataclass(frozen=True)
class Config:
    # Lighter
    lighter_account_id: str = field(default_factory=lambda: _require("LIGHTER_ACCOUNT_ID"))
    lighter_auth_token: str = field(default_factory=lambda: _require("LIGHTER_AUTH_TOKEN"))
    lighter_ws_url: str = field(
        default_factory=lambda: os.getenv(
            "LIGHTER_WS_URL", "wss://mainnet.zklighter.elliot.ai/stream"
        )
    )

    # Telegram
    telegram_bot_token: str = field(default_factory=lambda: _require("TELEGRAM_BOT_TOKEN"))
    telegram_channel_id: str = field(
        default_factory=lambda: _require("TELEGRAM_CHANNEL_ID")
    )

    # Pushover
    pushover_user_key: str | None = field(
        default_factory=lambda: os.getenv("PUSHOVER_USER_KEY") or None
    )

    # Redis
    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "redis"))
    redis_port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    redis_db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))
    redis_password: str | None = field(
        default_factory=lambda: os.getenv("REDIS_PASSWORD") or None
    )

    # SQLite
    database_path: str = field(
        default_factory=lambda: os.getenv("DATABASE_PATH", "/data/whale_tracker.db")
    )

    # Scheduler
    report_interval_minutes: int = field(
        default_factory=lambda: int(os.getenv("REPORT_INTERVAL_MINUTES", "5"))
    )
    sell_notify_cooldown_hours: int = field(
        default_factory=lambda: int(os.getenv("SELL_NOTIFY_COOLDOWN_HOURS", "2"))
    )

    # Notification links
    binance_pair_url: str = field(
        default_factory=lambda: os.getenv("BINANCE_PAIR_URL", "")
    )

    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


# Singleton – import this everywhere
settings = Config()
