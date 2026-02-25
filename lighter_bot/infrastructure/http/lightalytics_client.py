import asyncio
import json
import logging
import os
from datetime import UTC, datetime

import httpx
from pydantic import ValidationError

from lighter_bot.core.settings import Settings
from lighter_bot.domain.models import Trade, TradesResponse


class LightalyticsClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.headers = {
            "Sec-Fetch-Site": os.getenv("SEC_FETCH_SITE", "same-origin"),
            "Sec-Fetch-Mode": os.getenv("SEC_FETCH_MODE", "cors"),
            "Sec-Fetch-Dest": os.getenv("SEC_FETCH_DEST", "empty"),
            "X-La-Client": os.getenv("X_LA_CLIENT", "web"),
            "User-Agent": os.getenv(
                "USER_AGENT",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
            ),
        }
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            headers=self.headers,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def fetch_trades(self, window_start: datetime, window_end: datetime) -> list[Trade]:
        url = f"{self.settings.base_url}/accounts/{self.settings.account_id}/trades"
        params = {
            "aggregate": "true",
            "exchange": "lighter",
            "limit": str(self.settings.poll_limit),
            "from": self._format_ts(window_start),
            "to": self._format_ts(window_end),
        }

        for attempt in range(1, self.settings.max_retries + 1):
            try:
                response = await self._http.get(url, params=params)

                if response.status_code == 429:
                    wait_seconds = int(response.headers.get("Retry-After", "2"))
                    logging.warning("Rate limited by API (429). Retrying in %ss", wait_seconds)
                    await asyncio.sleep(wait_seconds)
                    continue

                if 500 <= response.status_code < 600:
                    wait_seconds = min(2**attempt, 10)
                    logging.warning(
                        "Server error %s on attempt %s/%s. Retrying in %ss",
                        response.status_code,
                        attempt,
                        self.settings.max_retries,
                        wait_seconds,
                    )
                    await asyncio.sleep(wait_seconds)
                    continue

                response.raise_for_status()
                payload = response.json()
                parsed = TradesResponse.model_validate(payload)
                return parsed.trades

            except httpx.TimeoutException:
                wait_seconds = min(2**attempt, 10)
                logging.warning(
                    "Request timeout on attempt %s/%s. Retrying in %ss",
                    attempt,
                    self.settings.max_retries,
                    wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
            except httpx.HTTPError:
                logging.exception("HTTP error while fetching trades")
                return []
            except ValidationError:
                logging.exception("Invalid API payload schema")
                return []
            except json.JSONDecodeError:
                logging.exception("API returned non-JSON response")
                return []

        logging.error("Failed to fetch trades after %s attempts", self.settings.max_retries)
        return []

    @staticmethod
    def _format_ts(value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
