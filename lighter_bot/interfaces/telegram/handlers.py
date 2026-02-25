import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from lighter_bot.infrastructure.persistence.subscription_store import SubscriptionStore


class TelegramCommandHandlers:
    def __init__(self, subscription_store: SubscriptionStore) -> None:
        self.subscription_store = subscription_store
        self.router = Router()
        self._register_handlers()

    def _register_handlers(self) -> None:
        @self.router.message(Command("enable_pushover"))
        async def enable_pushover(message: Message, command: CommandObject) -> None:
            if message.from_user is None:
                return

            user_key = (command.args or "").strip()
            if not user_key:
                await message.answer("Usage: /enable_pushover <user-key>")
                return

            try:
                await self.subscription_store.upsert_subscription(message.from_user.id, user_key)
                await message.answer("Pushover alerts enabled for your account.")
            except Exception:
                logging.exception("Failed enabling pushover for user_id=%s", message.from_user.id)
                await message.answer("Failed to enable Pushover alerts. Please try again.")

        @self.router.message(Command("disable_pushover"))
        async def disable_pushover(message: Message) -> None:
            if message.from_user is None:
                return

            try:
                deleted = await self.subscription_store.delete_subscription(message.from_user.id)
                if deleted > 0:
                    await message.answer("Pushover alerts disabled.")
                else:
                    await message.answer("You do not have active Pushover alerts.")
            except Exception:
                logging.exception("Failed disabling pushover for user_id=%s", message.from_user.id)
                await message.answer("Failed to disable Pushover alerts. Please try again.")
