"""
redis_client.py – async Redis helpers using Sorted Sets to store trades.

Key schema
----------
  trades:{account_id}   – Sorted Set; score = Unix timestamp (float);
                          member = JSON-encoded trade dict.

TTL policy
----------
  After every write the scheduler also calls `purge_old_trades()` which
  removes members older than TRADE_RETENTION_SECONDS (360 s = 6 min).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import redis.asyncio as aioredis

from bot.config import settings

logger = logging.getLogger(__name__)

# Trades older than this are removed from Redis (6 minutes)
TRADE_RETENTION_SECONDS: int = 360

_redis: aioredis.Redis | None = None


def _key(account_id: str) -> str:
    return f"trades:{account_id}"


async def get_redis() -> aioredis.Redis:
    """Return (and lazily create) the shared Redis connection pool."""
    global _redis
    if _redis is None:
        _redis = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
            decode_responses=True,
        )
        logger.info("Redis connection pool created (%s:%d)", settings.redis_host, settings.redis_port)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


# ─────────────────────────────────────────────────────────────────────────────
# Write helpers
# ─────────────────────────────────────────────────────────────────────────────

async def store_trades(account_id: str, trades: list[dict[str, Any]]) -> None:
    """
    Persist a batch of trades into the sorted set.

    Score  = ``_ts`` (Unix seconds, added by lighter_ws.py during enrichment).
    Member = JSON-encoded enriched trade dict, keyed by ``trade_id`` for
             deduplication.

    The Lighter API provides:
      - ``trade_id``  – unique integer ID for the trade
      - ``timestamp`` – milliseconds epoch (converted to ``_ts`` in seconds
                        by lighter_ws.py before this function is called)
    """
    if not trades:
        return

    r = await get_redis()
    mapping: dict[str, float] = {}
    for trade in trades:
        # _ts is set by lighter_ws.py (seconds); fall back to now if missing
        score = float(trade.get("_ts") or time.time())
        # trade_id is the canonical unique identifier from the Lighter API
        trade_id = trade.get("trade_id") or json.dumps(trade, sort_keys=True)
        member = json.dumps({**trade, "_member_id": str(trade_id)}, sort_keys=True)
        mapping[member] = score

    await r.zadd(_key(account_id), mapping)
    logger.debug("Stored %d trades for account %s", len(mapping), account_id)


async def purge_old_trades(account_id: str) -> int:
    """
    Remove trades older than TRADE_RETENTION_SECONDS from the sorted set.
    Returns the number of removed entries.
    """
    r = await get_redis()
    cutoff = time.time() - TRADE_RETENTION_SECONDS
    removed = await r.zremrangebyscore(_key(account_id), "-inf", cutoff)
    if removed:
        logger.debug("Purged %d old trades for account %s", removed, account_id)
    return removed


# ─────────────────────────────────────────────────────────────────────────────
# Read helpers
# ─────────────────────────────────────────────────────────────────────────────

async def get_recent_trades(
    account_id: str,
    window_seconds: int | None = None,
) -> list[dict[str, Any]]:
    """
    Return trades within the last ``window_seconds`` seconds (default: full retention window).
    Results are ordered by timestamp ascending.
    """
    if window_seconds is None:
        window_seconds = TRADE_RETENTION_SECONDS

    r = await get_redis()
    min_score = time.time() - window_seconds
    members = await r.zrangebyscore(_key(account_id), min_score, "+inf")
    return [json.loads(m) for m in members]
