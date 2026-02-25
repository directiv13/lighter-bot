"""
database.py – async SQLite helpers (aiosqlite).

Schema
------
users (
    user_id              INTEGER PRIMARY KEY,   -- Telegram user ID
    pushover_key         TEXT    NOT NULL,
    last_notification_at REAL    DEFAULT NULL    -- Unix timestamp of last Pushover alert
)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import aiosqlite

from bot.config import settings

logger = logging.getLogger(__name__)

_DB_PATH = settings.database_path


async def init_db() -> None:
    """Create tables if they do not exist yet."""
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id              INTEGER PRIMARY KEY,
                pushover_key         TEXT NOT NULL,
                last_notification_at REAL DEFAULT NULL
            )
            """
        )
        await db.commit()
    logger.info("Database initialised at %s", _DB_PATH)


# ─────────────────────────────────────────────────────────────────────────────
# CRUD helpers
# ─────────────────────────────────────────────────────────────────────────────

async def upsert_user(user_id: int, pushover_key: str) -> None:
    """Insert or update a user's Pushover key."""
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, pushover_key)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET pushover_key = excluded.pushover_key
            """,
            (user_id, pushover_key),
        )
        await db.commit()
    logger.debug("Upserted user %d", user_id)


async def delete_user(user_id: int) -> bool:
    """Remove a user. Returns True if a row was deleted."""
    async with aiosqlite.connect(_DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM users WHERE user_id = ?", (user_id,)
        )
        await db.commit()
        deleted = cursor.rowcount > 0
    if deleted:
        logger.debug("Deleted user %d", user_id)
    return deleted


async def get_all_users() -> list[dict]:
    """Return all subscribed users."""
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, pushover_key, last_notification_at FROM users"
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def update_last_notification(user_id: int) -> None:
    """Stamp the current time as last_notification_at for the user."""
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_notification_at = ? WHERE user_id = ?",
            (time.time(), user_id),
        )
        await db.commit()


async def get_user(user_id: int) -> Optional[dict]:
    """Fetch a single user row or None."""
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, pushover_key, last_notification_at FROM users WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None
