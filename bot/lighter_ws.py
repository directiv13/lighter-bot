"""
lighter_ws.py – persistent WebSocket connection to the Lighter exchange.

Actual message structure (from API)
-------------------------------------
{
    "channel": "account_all_trades:{ACCOUNT_ID}",
    "trades": {
        "{MARKET_ID}": [
            {
                "trade_id": 14879321842,
                "market_id": 132,
                "size": "1891",
                "price": "0.132360",
                "usd_amount": "250.292760",
                "bid_account_id": 714638,
                "ask_account_id": 54344,
                "is_maker_ask": true,
                "timestamp": 1772025303979,   # milliseconds
                ...
            }
        ]
    },
    "type": "update/account_all_trades"
}

Side detection
--------------
  bid_account_id == tracked_account  →  BUY  (our account placed the bid)
  ask_account_id == tracked_account  →  SELL (our account placed the ask)

Ping/pong
---------
  Server sends {"type": "ping"} – we must reply with {"type": "pong"}.

Reconnection
------------
  • Exponential back-off on errors.
  • The server silently drops every connection after 24 hours.  We force a
    clean reconnect after MAX_CONNECTION_AGE (23.5 h) so we never miss the
    server-side cut-off.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable

import websockets

from bot.config import settings
from bot.redis_client import purge_old_trades, store_trades

logger = logging.getLogger(__name__)

# Back-off config
_MIN_BACKOFF: float = 2.0    # seconds
_MAX_BACKOFF: float = 60.0   # seconds
_BACKOFF_FACTOR: float = 2.0

# Lighter drops every WS connection after 24 h – reconnect slightly before that
MAX_CONNECTION_AGE: float = 23.5 * 3600   # seconds


# ─────────────────────────────────────────────────────────────────────────────
# Side helpers  (operate on the enriched trade dict stored in Redis)
# ─────────────────────────────────────────────────────────────────────────────

def is_sell(trade: dict) -> bool:
    """Return True when the tracked account is on the ASK (sell) side."""
    return trade.get("_side") == "sell"


def is_buy(trade: dict) -> bool:
    """Return True when the tracked account is on the BID (buy) side."""
    return trade.get("_side") == "buy"


def _resolve_side(trade: dict, account_id_int: int) -> str:
    """
    Derive which side of the trade our account is on.

    The Lighter API uses ``bid_account_id`` / ``ask_account_id`` rather than
    an explicit ``side`` field.
    """
    if trade.get("bid_account_id") == account_id_int:
        return "buy"
    if trade.get("ask_account_id") == account_id_int:
        return "sell"
    return "unknown"


class LighterWebSocketClient:
    """
    Async WebSocket client for the Lighter exchange.

    Parameters
    ----------
    on_sell_callback:
        Async callable invoked for *each individual sell trade* as it arrives.
        Signature: ``async def cb(trade: dict) -> None``
    """

    def __init__(
        self,
        on_sell_callback: Callable[[dict], Awaitable[None]],
    ) -> None:
        self._on_sell = on_sell_callback
        self._running = False
        self._task: asyncio.Task | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> asyncio.Task:
        """Spawn the background connection task and return it."""
        self._running = True
        self._task = asyncio.create_task(self._run(), name="lighter_ws")
        return self._task

    async def stop(self) -> None:
        """Gracefully stop the background task."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        backoff = _MIN_BACKOFF
        while self._running:
            try:
                await self._connect_and_listen()
                # Clean return (e.g. MAX_CONNECTION_AGE hit) – reconnect immediately
                backoff = _MIN_BACKOFF
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(
                    "WebSocket error: %s – reconnecting in %.1fs", exc, backoff
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * _BACKOFF_FACTOR, _MAX_BACKOFF)

    async def _connect_and_listen(self) -> None:
        account_id = settings.lighter_account_id
        logger.info("Connecting to Lighter WebSocket %s", settings.lighter_ws_url)

        async with websockets.connect(
            settings.lighter_ws_url,
            # Disable websockets' own ping frames – the Lighter protocol uses
            # application-level {"type": "ping"} / {"type": "pong"} messages.
            ping_interval=None,
            close_timeout=10,
        ) as ws:
            logger.info(
                "Connected. Subscribing to account_all_trades/%s", account_id
            )
            await ws.send(
                json.dumps(
                    {
                        "type": "subscribe",
                        "channel": f"account_all_trades/{account_id}",
                        "auth": settings.lighter_auth_token,
                    }
                )
            )

            # Run the receive loop until MAX_CONNECTION_AGE, then return so
            # _run() can open a fresh connection.
            try:
                await asyncio.wait_for(
                    self._receive_loop(ws),
                    timeout=MAX_CONNECTION_AGE,
                )
            except asyncio.TimeoutError:
                logger.info(
                    "Max connection age (%.1f h) reached – reconnecting …",
                    MAX_CONNECTION_AGE / 3600,
                )

    async def _receive_loop(self, ws) -> None:
        """Consume messages until the connection closes or we are stopped."""
        async for raw_msg in ws:
            if not self._running:
                break
            try:
                await self._handle_message(ws, raw_msg)
            except Exception as exc:
                logger.exception("Error handling WS message: %s", exc)

    async def _handle_message(self, ws, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Received non-JSON message: %.200s", raw)
            return

        msg_type = msg.get("type", "")

        # ── Application-level ping/pong ───────────────────────────────────────
        if msg_type == "ping":
            await ws.send(json.dumps({"type": "pong"}))
            logger.debug("Replied to server ping with pong")
            return

        # ── Trade updates ─────────────────────────────────────────────────────
        if msg_type not in ("update/account_all_trades", "account_all_trades"):
            logger.debug("Ignoring message type: %s", msg_type)
            return

        account_id_str = settings.lighter_account_id
        account_id_int = int(account_id_str)
        trades_by_market: dict[str, list[dict]] = msg.get("trades") or {}

        all_trades: list[dict] = []
        sell_trades: list[dict] = []
        now = time.time()

        for _market_key, trade_list in trades_by_market.items():
            for trade in trade_list:
                side = _resolve_side(trade, account_id_int)

                # Convert Lighter millisecond timestamp to Unix seconds
                ts_ms = trade.get("timestamp")
                ts_sec = (ts_ms / 1000.0) if ts_ms else now

                enriched = {
                    **trade,
                    # Normalised helpers used by scheduler / pushover
                    "_side": side,
                    "_ts": ts_sec,          # seconds (Redis score)
                    "_usd": float(trade.get("usd_amount") or 0),
                    "_market": str(trade.get("market_id", _market_key)),
                    "_account_id": account_id_str,
                    "_received_at": now,
                }
                all_trades.append(enriched)
                if side == "sell":
                    sell_trades.append(enriched)

        # Persist all trades
        if all_trades:
            await store_trades(account_id_str, all_trades)
            await purge_old_trades(account_id_str)
            logger.debug(
                "Processed %d trades (%d sells) for account %s",
                len(all_trades),
                len(sell_trades),
                account_id_str,
            )

        # Fire sell callback immediately
        for sell_trade in sell_trades:
            try:
                await self._on_sell(sell_trade)
            except Exception as exc:
                logger.exception("on_sell_callback raised: %s", exc)
