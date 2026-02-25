import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path


class StateStore:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self._lock = asyncio.Lock()

    async def load_last_ts(self) -> datetime | None:
        async with self._lock:
            if not self.file_path.exists():
                return None

            try:
                raw = json.loads(self.file_path.read_text(encoding="utf-8"))
                ts = raw.get("last_ts")
                if not ts:
                    return None
                return datetime.fromisoformat(ts)
            except (json.JSONDecodeError, ValueError, OSError):
                logging.exception("Failed loading state file; continuing without state")
                return None

    async def save_last_ts(self, timestamp: datetime) -> None:
        async with self._lock:
            try:
                payload = {"last_ts": timestamp.isoformat()}
                self.file_path.write_text(json.dumps(payload), encoding="utf-8")
            except OSError:
                logging.exception("Failed writing state file")
