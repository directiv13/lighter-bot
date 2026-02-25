"""
telegram_bot.py – Telegram bot command handlers.

Commands
--------
/start              – Welcome message.
/help               – List available commands.
/enable_pushover <user-key>
                    – Register the caller's Pushover user key.
/disable_pushover   – Unsubscribe the caller from Pushover alerts.
/status             – Show subscriber count and bot health.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from bot.config import settings
from bot.database import delete_user, get_all_users, upsert_user

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Handlers
# ─────────────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 <b>Lighter Whale Tracker</b>\n\n"
        "I monitor a Lighter DEX whale account and send trade reports to this channel "
        "every few minutes.\n\n"
        "Use /help to see available commands.",
        parse_mode="HTML",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "<b>Available commands</b>\n\n"
        "/enable_pushover <i>your-pushover-user-key</i>\n"
        "  → Subscribe to instant sell alerts via Pushover.\n\n"
        "/disable_pushover\n"
        "  → Unsubscribe from Pushover alerts.\n\n"
        "/status\n"
        "  → Show bot status and subscriber count.",
        parse_mode="HTML",
    )


async def cmd_enable_pushover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text(
            "⚠️ Usage: <code>/enable_pushover your-pushover-user-key</code>",
            parse_mode="HTML",
        )
        return

    pushover_key = context.args[0].strip()
    if len(pushover_key) < 10:
        await update.message.reply_text(
            "⚠️ That doesn't look like a valid Pushover user key. "
            "Please copy it from your Pushover dashboard."
        )
        return

    await upsert_user(user_id, pushover_key)
    await update.message.reply_text(
        "✅ You have been subscribed to Pushover sell alerts.\n"
        f"Cooldown between alerts: {settings.sell_notify_cooldown_hours} h.",
    )
    logger.info("User %d enabled Pushover", user_id)


async def cmd_disable_pushover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    deleted = await delete_user(user_id)
    if deleted:
        await update.message.reply_text("✅ You have been unsubscribed from Pushover alerts.")
        logger.info("User %d disabled Pushover", user_id)
    else:
        await update.message.reply_text(
            "ℹ️ You were not subscribed. Use /enable_pushover to subscribe."
        )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    users = await get_all_users()
    account = settings.lighter_account_id
    interval = settings.report_interval_minutes
    await update.message.reply_text(
        f"🤖 <b>Bot status</b>\n\n"
        f"Tracked account: <code>{account}</code>\n"
        f"Report interval: {interval} min\n"
        f"Pushover subscribers: {len(users)}",
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Application factory
# ─────────────────────────────────────────────────────────────────────────────

def build_application() -> Application:
    """Create and configure the python-telegram-bot Application."""
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("enable_pushover", cmd_enable_pushover))
    app.add_handler(CommandHandler("disable_pushover", cmd_disable_pushover))
    app.add_handler(CommandHandler("status", cmd_status))

    return app
