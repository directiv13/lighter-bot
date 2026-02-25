import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from aiogram import Bot

from lighter_bot.core.settings import Settings
from lighter_bot.domain.models import Trade
from lighter_bot.infrastructure.http.lightalytics_client import LightalyticsClient
from lighter_bot.infrastructure.http.pushover_client import PushoverClient
from lighter_bot.infrastructure.persistence.state_store import StateStore
from lighter_bot.infrastructure.persistence.subscription_store import SubscriptionStore


class TradeMonitorService:
    def __init__(
        self,
        settings: Settings,
        bot: Bot,
        state_store: StateStore,
        subscription_store: SubscriptionStore,
        lightalytics_client: LightalyticsClient,
        pushover_client: PushoverClient,
    ) -> None:
        self.settings = settings
        self.bot = bot
        self.state_store = state_store
        self.subscription_store = subscription_store
        self.lightalytics_client = lightalytics_client
        self.pushover_client = pushover_client
        self._job_lock = asyncio.Lock()

    async def run_once(self) -> None:
        if self._job_lock.locked():
            logging.warning("Previous poll still running; skipping overlapping run")
            return

        async with self._job_lock:
            now = datetime.now(tz=UTC)
            window_end = now.replace(second=0, microsecond=0)
            window_start = window_end - timedelta(minutes=5)

            logging.info(
                "Polling trades from %s to %s",
                window_start.isoformat(),
                window_end.isoformat(),
            )

            trades = await self.lightalytics_client.fetch_trades(window_start, window_end)
            if not trades:
                return

            last_processed_ts = await self.state_store.load_last_ts()
            fresh_trades = [
                trade
                for trade in sorted(trades, key=lambda item: item.ts)
                if last_processed_ts is None or trade.ts > last_processed_ts
            ]

            if not fresh_trades:
                logging.info("No new trades after deduplication")
                return

            total_buy = Decimal("0")
            total_sell = Decimal("0")

            for trade in fresh_trades:
                if trade.direction == "Buy":
                    total_buy += trade.usd_size
                elif trade.direction == "Sell":
                    total_sell += trade.usd_size
                    await self._send_sell_alert(trade)
                    await self._send_pushover_sell_alert(trade)

            if total_buy > 0 or total_sell > 0:
                await self._send_summary(total_buy, total_sell)

            latest_ts = max(trade.ts for trade in fresh_trades)
            await self.state_store.save_last_ts(latest_ts)
            logging.info("Processed %s new trades", len(fresh_trades))

    async def _send_sell_alert(self, trade: Trade) -> None:
        message = (
            "🔴 SELL detected\n"
            f"Time: {trade.ts.astimezone(UTC).isoformat()}\n"
            f"USD Size: ${trade.usd_size:,.2f}"
        )
        await self._safe_send(message)

    async def _send_summary(self, total_buy: Decimal, total_sell: Decimal) -> None:
        message = f"Total Buy: ${total_buy:,.2f}, Total Sell: ${total_sell:,.2f}"
        await self._safe_send(message)

    async def _send_pushover_sell_alert(self, trade: Trade) -> None:
        cooldown = timedelta(minutes=self.settings.notification_cooldown_minutes)
        subscriptions = await self.subscription_store.list_eligible_subscriptions(cooldown)

        if not subscriptions:
            return

        now = datetime.now(tz=UTC)
        for subscription in subscriptions:
            sent = await self.pushover_client.send_sell_notification(
                user_key=subscription.pushover_user_key,
                trade=trade,
            )
            if sent:
                await self.subscription_store.mark_notified(subscription.user_id, now)

    async def _safe_send(self, text: str) -> None:
        try:
            await self.bot.send_message(chat_id=self.settings.channel_id, text=text)
        except Exception:
            logging.exception("Failed sending Telegram message")
