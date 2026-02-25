from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite

from lighter_bot.domain.models import Subscription


class SubscriptionStore:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.file_path)
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pushover_subscriptions (
                user_id INTEGER PRIMARY KEY,
                pushover_user_key TEXT NOT NULL,
                last_notification_at TEXT NULL
            )
            """
        )
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def upsert_subscription(self, user_id: int, pushover_user_key: str) -> None:
        conn = self._get_conn()
        await conn.execute(
            """
            INSERT INTO pushover_subscriptions(user_id, pushover_user_key, last_notification_at)
            VALUES(?, ?, NULL)
            ON CONFLICT(user_id)
            DO UPDATE SET pushover_user_key=excluded.pushover_user_key
            """,
            (user_id, pushover_user_key),
        )
        await conn.commit()

    async def delete_subscription(self, user_id: int) -> int:
        conn = self._get_conn()
        cursor = await conn.execute(
            "DELETE FROM pushover_subscriptions WHERE user_id = ?",
            (user_id,),
        )
        await conn.commit()
        return cursor.rowcount

    async def list_eligible_subscriptions(self, cooldown: timedelta) -> list[Subscription]:
        conn = self._get_conn()
        cutoff = (datetime.now(tz=UTC) - cooldown).isoformat()
        cursor = await conn.execute(
            """
            SELECT user_id, pushover_user_key
            FROM pushover_subscriptions
            WHERE last_notification_at IS NULL OR last_notification_at <= ?
            """,
            (cutoff,),
        )
        rows = await cursor.fetchall()
        return [Subscription(user_id=row[0], pushover_user_key=row[1]) for row in rows]

    async def mark_notified(self, user_id: int, at: datetime) -> None:
        conn = self._get_conn()
        await conn.execute(
            "UPDATE pushover_subscriptions SET last_notification_at = ? WHERE user_id = ?",
            (at.isoformat(), user_id),
        )
        await conn.commit()

    def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("SubscriptionStore is not connected")
        return self._conn
