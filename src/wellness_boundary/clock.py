"""可控时钟：为期限引擎提供可注入的时间源。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol


def require_aware(value: datetime, field: str = "时间") -> datetime:
    """所有进入领域的时间都必须携带时区。"""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field}必须携带时区")
    return value


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass
class ManualClock:
    """测试与监管演练使用的可控时钟。"""

    current: datetime

    def __post_init__(self) -> None:
        require_aware(self.current, "时钟初始时间")

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current = self.current + delta
