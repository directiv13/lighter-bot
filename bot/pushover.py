"""
pushover.py – send Pushover notifications to subscribed users.

Spam-prevention
---------------
Each user has a ``last_notification_at`` timestamp in SQLite.
A notification is sent only if that timestamp is NULL or older than
``SELL_NOTIFY_COOLDOWN_HOURS`` (default 2 h).
"""

from __future__ import annotations

import logging
import time

import httpx

from bot.config import settings
from bot.database import get_all_users, update_last_notification

logger = logging.getLogger(__name__)

PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"
PUSHOVER_APP_TOKEN = "lighter_whale_tracker"   # static app token; keep neutral

# Cooldown in seconds
_COOLDOWN_SECONDS: float = settings.sell_notify_cooldown_hours * 3600


async def notify_sell(trade: dict) -> None:
    """
    Notify all subscribed users about a sell trade, respecting the cooldown.

    Parameters
    ----------
    trade:
        The enriched trade dict from lighter_ws.py.
    """
    users = await get_all_users()
    if not users:
        return

    now = time.time()
    market = trade.get("_market") or trade.get("market_id", "?")
    price = trade.get("price", "?")
    size = trade.get("size", "?")
    usd = trade.get("_usd") or trade.get("usd_amount", "?")
    msg_title = "🐋 Lighter Whale SELL"
    msg_body = (
        f"Market: {market}\n"
        f"Price: {price}\n"
        f"Size: {size}\n"
        f"USD: ${float(usd):,.2f}\n"
        f"Account: {settings.lighter_account_id}"
    )

    async with httpx.AsyncClient(timeout=10) as client:
        for user in users:
            last_notified: float | None = user["last_notification_at"]
            if last_notified and (now - last_notified) < _COOLDOWN_SECONDS:
                remaining = _COOLDOWN_SECONDS - (now - last_notified)
                logger.debug(
                    "Skipping Pushover for user %d – cooldown %.0fs remaining",
                    user["user_id"],
                    remaining,
                )
                continue

            try:
                resp = await client.post(
                    PUSHOVER_API_URL,
                    data={
                        "token": PUSHOVER_APP_TOKEN,
                        "user": user["pushover_key"],
                        "title": msg_title,
                        "message": msg_body,
                        "priority": 0,
                    },
                )
                if resp.status_code == 200:
                    await update_last_notification(user["user_id"])
                    logger.info("Pushover sent to user %d", user["user_id"])
                else:
                    logger.warning(
                        "Pushover API error %d for user %d: %s",
                        resp.status_code,
                        user["user_id"],
                        resp.text,
                    )
            except httpx.RequestError as exc:
                logger.error("Pushover HTTP request failed for user %d: %s", user["user_id"], exc)
