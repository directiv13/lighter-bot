from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class Trade(BaseModel):
    ts: datetime
    direction: Literal["Buy", "Sell"]
    usd_size: Decimal


class TradesResponse(BaseModel):
    trades: list[Trade]


@dataclass(frozen=True)
class Subscription:
    user_id: int
    pushover_user_key: str
