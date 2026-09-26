"""可控时钟。

期限引擎与案卷服务不直接读取系统时间，而是通过 ``Clock`` 获取当前时刻，
测试可以用 ``ManualClock`` 精确推进冷静期、补证、整改和退款倒计时。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from .errors import DomainError


def ensure_aware(value: datetime, field: str = "occurred_at") -> datetime:
    """要求时间必须携带时区，与事件契约保持一致。"""
    if not isinstance(value, datetime):
        raise DomainError(f"{field} 必须是 datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainError(f"{field} 必须携带时区")
    return value


def to_iso(value: datetime) -> str:
    """序列化为带时区的 ISO 字符串。"""
    return ensure_aware(value).isoformat()


class Clock(Protocol):
    def now(self) -> datetime: ...


@dataclass
class SystemClock:
    """生产环境时钟，返回 UTC 当前时间。"""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass
class ManualClock:
    """测试与演练用的可控时钟。"""

    current: datetime

    def __post_init__(self) -> None:
        ensure_aware(self.current, "current")

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> datetime:
        self.current = self.current + delta
        return self.current

    def set(self, value: datetime) -> datetime:
        self.current = ensure_aware(value, "current")
        return self.current
