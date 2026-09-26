"""期限引擎：冷静期、补证、整改与退款倒计时。

服务暂停时冻结剩余时间，恢复后继续原有倒计时而不是重新开始。
所有时间判断都通过注入的可控时钟完成。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from .clock import Clock


class DeadlineKind(Enum):
    COOLING_OFF = "cooling_off"                    # 冷静期
    EVIDENCE_SUPPLEMENT = "evidence_supplement"    # 补证
    RECTIFICATION = "rectification"                # 整改
    REFUND = "refund"                              # 退款


class DeadlineStatus(Enum):
    RUNNING = "running"
    PAUSED = "paused"
    EXPIRED = "expired"
    COMPLETED = "completed"


@dataclass
class _Deadline:
    kind: DeadlineKind
    remaining: timedelta
    started_at: datetime
    paused: bool = False
    completed: bool = False


class DeadlineEngine:
    """按案件管理期限，时钟由调用方注入。"""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._deadlines: dict[tuple[str, DeadlineKind], _Deadline] = {}

    def start(self, case_ref: str, kind: DeadlineKind, duration: timedelta) -> None:
        if duration <= timedelta(0):
            raise ValueError("期限长度必须为正")
        key = (case_ref, kind)
        if key in self._deadlines:
            raise ValueError("该期限已经存在，不能重复启动")
        self._deadlines[key] = _Deadline(kind=kind, remaining=duration, started_at=self._clock.now())

    def _get(self, case_ref: str, kind: DeadlineKind) -> _Deadline:
        try:
            return self._deadlines[(case_ref, kind)]
        except KeyError:
            raise KeyError(f"案件 {case_ref} 不存在 {kind.value} 期限") from None

    def pause(self, case_ref: str, kind: DeadlineKind) -> None:
        """服务暂停：冻结剩余时间。"""
        deadline = self._get(case_ref, kind)
        if deadline.completed:
            raise ValueError("期限已完成，不能暂停")
        if deadline.paused:
            raise ValueError("期限已处于暂停状态")
        deadline.remaining = self._live_remaining(deadline)
        deadline.paused = True

    def resume(self, case_ref: str, kind: DeadlineKind) -> None:
        """服务恢复：继续原有倒计时，剩余时间不变。"""
        deadline = self._get(case_ref, kind)
        if deadline.completed:
            raise ValueError("期限已完成，不能恢复")
        if not deadline.paused:
            raise ValueError("期限未暂停，不能恢复")
        deadline.started_at = self._clock.now()
        deadline.paused = False

    def complete(self, case_ref: str, kind: DeadlineKind) -> None:
        """义务提前履行完毕，期限终止。"""
        deadline = self._get(case_ref, kind)
        deadline.remaining = self.remaining(case_ref, kind)
        deadline.completed = True
        deadline.paused = False

    def _live_remaining(self, deadline: _Deadline) -> timedelta:
        elapsed = self._clock.now() - deadline.started_at
        return deadline.remaining - elapsed

    def remaining(self, case_ref: str, kind: DeadlineKind) -> timedelta:
        deadline = self._get(case_ref, kind)
        if deadline.completed or deadline.paused:
            return max(deadline.remaining, timedelta(0))
        return max(self._live_remaining(deadline), timedelta(0))

    def status(self, case_ref: str, kind: DeadlineKind) -> DeadlineStatus:
        deadline = self._get(case_ref, kind)
        if deadline.completed:
            return DeadlineStatus.COMPLETED
        if deadline.paused:
            return DeadlineStatus.PAUSED
        if self._live_remaining(deadline) <= timedelta(0):
            return DeadlineStatus.EXPIRED
        return DeadlineStatus.RUNNING

    def is_expired(self, case_ref: str, kind: DeadlineKind) -> bool:
        return self.status(case_ref, kind) is DeadlineStatus.EXPIRED
