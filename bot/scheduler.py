"""
scheduler.py – APScheduler job that posts the 5-minute cumulative trade report
to the Telegram channel.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import settings
from bot.redis_client import get_recent_trades

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()
_bot_ref = None   # will be set by main.py


def set_bot(bot) -> None:
    """Inject the telegram.Bot instance from main.py."""
    global _bot_ref
    _bot_ref = bot


def start_scheduler() -> None:
    """Register and start the background scheduler."""
    _scheduler.add_job(
        _post_trade_report,
        trigger="interval",
        minutes=settings.report_interval_minutes,
        id="trade_report",
        replace_existing=True,
        misfire_grace_time=30,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started – trade report interval: %d min",
        settings.report_interval_minutes,
    )


def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)


# ─────────────────────────────────────────────────────────────────────────────
# Report builder
# ─────────────────────────────────────────────────────────────────────────────

async def _post_trade_report() -> None:
    """Fetch recent trades from Redis, summarise, and post to Telegram."""
    if _bot_ref is None:
        logger.warning("Bot reference not set – skipping report")
        return

    account_id = settings.lighter_account_id
    window = settings.report_interval_minutes * 60  # seconds

    try:
        trades = await get_recent_trades(account_id, window_seconds=window)
    except Exception as exc:
        logger.error("Failed to fetch trades from Redis: %s", exc)
        return

    if not trades:
        logger.debug("No trades in the last %d minutes – skipping report", settings.report_interval_minutes)
        return

    # Aggregate per market
    # Trades are enriched by lighter_ws.py with normalised helpers:
    #   _side   : "buy" | "sell" | "unknown"
    #   _usd    : float  – usd_amount from the API (pre-calculated)
    #   _market : str    – market_id as a string
    market_stats: dict[str, dict] = {}
    total_buy_volume = 0.0
    total_sell_volume = 0.0

    for trade in trades:
        mkt = trade.get("_market") or str(trade.get("market_id", "unknown"))
        stats = market_stats.setdefault(mkt, {"buy_count": 0, "sell_count": 0, "buy_vol": 0.0, "sell_vol": 0.0})

        usd = float(trade.get("_usd") or trade.get("usd_amount") or 0)

        side = trade.get("_side", "unknown")
        if side == "buy":
            stats["buy_count"] += 1
            stats["buy_vol"] += usd
            total_buy_volume += usd
        elif side == "sell":
            stats["sell_count"] += 1
            stats["sell_vol"] += usd
            total_sell_volume += usd

    now_utc = datetime.now(timezone.utc).strftime("%H:%M UTC")
    lines = [
        f"🐋 <b>Lighter Whale Report</b>  <i>{now_utc}</i>",
        f"Account: <code>{account_id}</code>",
        f"Window: last {settings.report_interval_minutes} min",
        "",
        f"📈 <b>Total BUY  volume:</b>  ${total_buy_volume:,.2f}",
        f"📉 <b>Total SELL volume:</b>  ${total_sell_volume:,.2f}",
    ]

    if len(market_stats) > 1:
        lines.append("")
        lines.append("<b>Per-market breakdown:</b>")
        for mkt, s in sorted(market_stats.items()):
            lines.append(
                f"  Market {mkt}: "
                f"↑{s['buy_count']} (${s['buy_vol']:,.2f})  "
                f"↓{s['sell_count']} (${s['sell_vol']:,.2f})"
            )

    message = "\n".join(lines)

    try:
        await _bot_ref.send_message(
            chat_id=settings.telegram_channel_id,
            text=message,
            parse_mode="HTML",
        )
        logger.info("Trade report posted to Telegram channel")
    except Exception as exc:
        logger.error("Failed to post trade report: %s", exc)
