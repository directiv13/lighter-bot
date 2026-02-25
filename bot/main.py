"""
main.py – entry point.

Start-up sequence
-----------------
1. Configure logging.
2. Initialise SQLite schema.
3. Build Telegram Application.
4. Start the APScheduler (5-min report job).
5. Start the Lighter WebSocket client (background task).
6. Run the Telegram bot (polling – blocks until SIGINT/SIGTERM).
7. Graceful shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from bot.config import settings
from bot.database import init_db
from bot.lighter_ws import LighterWebSocketClient
from bot.pushover import notify_sell
from bot.redis_client import close_redis
from bot.scheduler import set_bot, start_scheduler, stop_scheduler
from bot.telegram_bot import build_application


def _configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "websockets", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


async def main() -> None:
    _configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Lighter Whale Tracker …")

    # ── Database ──────────────────────────────────────────────────────────────
    await init_db()

    # ── Telegram bot ──────────────────────────────────────────────────────────
    app = build_application()
    await app.initialize()
    await app.start()

    # Share the bot instance with the scheduler
    set_bot(app.bot)

    # ── Scheduler ─────────────────────────────────────────────────────────────
    start_scheduler()

    # ── Lighter WebSocket ─────────────────────────────────────────────────────
    ws_client = LighterWebSocketClient(on_sell_callback=notify_sell)
    _ws_task = ws_client.start()

    logger.info("All services started. Waiting for updates …")

    # ── Polling ───────────────────────────────────────────────────────────────
    # Start polling in a background thread-friendly way
    await app.updater.start_polling(drop_pending_updates=True)

    # ── Shutdown handling ─────────────────────────────────────────────────────
    stop_event = asyncio.Event()

    def _sig_handler(*_):
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_event_loop().add_signal_handler(sig, _sig_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler for SIGTERM
            signal.signal(sig, _sig_handler)

    await stop_event.wait()

    # ── Graceful shutdown ─────────────────────────────────────────────────────
    logger.info("Shutting down …")
    stop_scheduler()
    await ws_client.stop()
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    await close_redis()
    logger.info("Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
