import asyncio
import json
import logging

import httpx

from lighter_bot.core.settings import Settings
from lighter_bot.domain.models import Trade


class PushoverClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(settings.request_timeout_seconds))

    async def close(self) -> None:
        await self._http.aclose()

    async def send_sell_notification(self, user_key: str, trade: Trade) -> bool:
        payload = {
            "token": self.settings.pushover_app_token,
            "user": user_key,
            "title": "Lighter SELL Alert",
            "message": (
                f"SELL detected at {trade.ts.isoformat()} | "
                f"USD Size: ${trade.usd_size:,.2f}"
            ),
        }

        for attempt in range(1, self.settings.max_retries + 1):
            try:
                response = await self._http.post(
                    "https://api.pushover.net/1/messages.json",
                    data=payload,
                )

                if response.status_code == 429:
                    wait_seconds = int(response.headers.get("Retry-After", "2"))
                    logging.warning("Pushover rate limited (429). Retrying in %ss", wait_seconds)
                    await asyncio.sleep(wait_seconds)
                    continue

                if 500 <= response.status_code < 600:
                    wait_seconds = min(2**attempt, 10)
                    logging.warning(
                        "Pushover server error %s on attempt %s/%s. Retrying in %ss",
                        response.status_code,
                        attempt,
                        self.settings.max_retries,
                        wait_seconds,
                    )
                    await asyncio.sleep(wait_seconds)
                    continue

                response.raise_for_status()
                data = response.json()
                return bool(data.get("status") == 1)

            except httpx.TimeoutException:
                wait_seconds = min(2**attempt, 10)
                logging.warning(
                    "Pushover timeout on attempt %s/%s. Retrying in %ss",
                    attempt,
                    self.settings.max_retries,
                    wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
            except (httpx.HTTPError, json.JSONDecodeError):
                logging.exception("Failed sending Pushover notification")
                return False

        logging.error("Failed to send Pushover notification after %s attempts", self.settings.max_retries)
        return False
