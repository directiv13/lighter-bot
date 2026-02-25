import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    channel_id: str
    pushover_app_token: str
    account_id: int = 714638
    base_url: str = "https://lightalytics.com/api/v1"
    state_file: Path = Path("state.json")
    db_file: Path = Path("subscriptions.db")
    poll_limit: int = 500
    notification_cooldown_minutes: int = 120
    request_timeout_seconds: float = 15.0
    max_retries: int = 3

    @staticmethod
    def from_env() -> "Settings":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        channel_id = os.getenv("CHANNEL_ID", "").strip()
        pushover_app_token = os.getenv("PUSHOVER_APP_TOKEN", "").strip()

        if not token:
            raise ValueError("Missing required env var: TELEGRAM_BOT_TOKEN")
        if not channel_id:
            raise ValueError("Missing required env var: CHANNEL_ID")
        if not pushover_app_token:
            raise ValueError("Missing required env var: PUSHOVER_APP_TOKEN")

        return Settings(
            telegram_bot_token=token,
            channel_id=channel_id,
            pushover_app_token=pushover_app_token,
            account_id=int(os.getenv("LIGHTALYTICS_ACCOUNT_ID", "714638")),
            state_file=Path(os.getenv("STATE_FILE", "state.json")),
            db_file=Path(os.getenv("DB_FILE", "subscriptions.db")),
            poll_limit=int(os.getenv("POLL_LIMIT", "500")),
            notification_cooldown_minutes=int(os.getenv("NOTIFICATION_COOLDOWN_MINUTES", "120")),
        )
