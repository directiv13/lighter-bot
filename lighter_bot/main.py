import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from lighter_bot.application.trade_monitor_service import TradeMonitorService
from lighter_bot.core.settings import Settings
from lighter_bot.infrastructure.http.lightalytics_client import LightalyticsClient
from lighter_bot.infrastructure.http.pushover_client import PushoverClient
from lighter_bot.infrastructure.persistence.state_store import StateStore
from lighter_bot.infrastructure.persistence.subscription_store import SubscriptionStore
from lighter_bot.interfaces.telegram.handlers import TelegramCommandHandlers


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    settings = Settings.from_env()
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()

    state_store = StateStore(settings.state_file)
    subscription_store = SubscriptionStore(settings.db_file)
    lightalytics_client = LightalyticsClient(settings)
    pushover_client = PushoverClient(settings)

    handlers = TelegramCommandHandlers(subscription_store)
    dispatcher.include_router(handlers.router)

    service = TradeMonitorService(
        settings=settings,
        bot=bot,
        state_store=state_store,
        subscription_store=subscription_store,
        lightalytics_client=lightalytics_client,
        pushover_client=pushover_client,
    )

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        service.run_once,
        trigger=CronTrigger(minute="*/5", second=0),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )

    await subscription_store.connect()
    await bot.set_my_commands(
        [
            BotCommand(command="enable_pushover", description="Enable Pushover sell alerts"),
            BotCommand(command="disable_pushover", description="Disable Pushover sell alerts"),
        ]
    )

    try:
        await service.run_once()
        scheduler.start()
        logging.info("Trade monitor bot started; Telegram command polling is active")
        await dispatcher.start_polling(bot)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logging.info("Shutdown requested")
    finally:
        scheduler.shutdown(wait=False)
        await lightalytics_client.close()
        await pushover_client.close()
        await subscription_store.close()
        await bot.session.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
