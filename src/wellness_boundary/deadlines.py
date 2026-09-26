"""期限引擎：以可控时钟驱动冷静期、补证、整改和退款倒计时。

服务暂停时倒计时冻结，服务恢复后**继续原有倒计时**——剩余期限不因暂停而
重置，暂停时长不计入已耗时间。到期判定只在倒计时运行中进行；暂停中的期限
即使墙钟时间早已越过终点也不算到期。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from .clock import Clock, ensure_aware
from .errors import DeadlineNotFoundError, DeadlineStateError, DomainError


class DeadlineKind(str, Enum):
    COOLING_OFF = "cooling_off"  # 冷静期
    EVIDENCE_SUPPLEMENT = "evidence_supplement"  # 补证
    RECTIFICATION = "rectification"  # 整改
    REFUND = "refund"  # 退款


class DeadlineStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"  # 服务暂停，倒计时冻结
    COMPLETED = "completed"
    CANCELLED = "cancelled"


_ACTIVE_STATUSES = {DeadlineStatus.RUNNING, DeadlineStatus.PAUSED}


@dataclass
class Deadline:
    deadline_id: str
    case_id: str
    kind: DeadlineKind
    duration: timedelta
    started_at: datetime
    status: DeadlineStatus = DeadlineStatus.RUNNING
    paused_at: datetime | None = None
    accumulated_pause: timedelta = timedelta(0)
    pause_reason: str | None = None
    closed_at: datetime | None = None

    def _active_elapsed(self, now: datetime) -> timedelta:
        """扣除暂停时长后的实际已耗时间。"""
        end = self.paused_at if self.status is DeadlineStatus.PAUSED else now
        return (end - self.started_at) - self.accumulated_pause

    def remaining(self, now: datetime) -> timedelta:
        if self.status not in _ACTIVE_STATUSES:
            return timedelta(0)
        return max(timedelta(0), self.duration - self._active_elapsed(now))

    def is_expired(self, now: datetime) -> bool:
        return (
            self.status is DeadlineStatus.RUNNING
            and self._active_elapsed(now) >= self.duration
        )


class DeadlineEngine:
    """按案卷管理期限，所有判定都以注入的时钟为准。"""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._deadlines: dict[str, Deadline] = {}
        self._sequence = 0
        self._lock = threading.Lock()

    def open(
        self,
        case_id: str,
        kind: DeadlineKind,
        duration: timedelta,
        *,
        deadline_id: str | None = None,
    ) -> Deadline:
        if duration <= timedelta(0):
            raise DomainError("期限时长必须为正")
        with self._lock:
            self._sequence += 1
            deadline = Deadline(
                deadline_id=deadline_id or f"DL-{self._sequence:06d}",
                case_id=case_id,
                kind=kind,
                duration=duration,
                started_at=self._clock.now(),
            )
            if deadline.deadline_id in self._deadlines:
                raise DomainError(f"期限标识重复：{deadline.deadline_id}")
            self._deadlines[deadline.deadline_id] = deadline
            return deadline

    def get(self, deadline_id: str) -> Deadline:
        try:
            return self._deadlines[deadline_id]
        except KeyError:
            raise DeadlineNotFoundError(f"期限不存在：{deadline_id}") from None

    def pause(self, deadline_id: str, reason: str = "") -> Deadline:
        """服务暂停：冻结倒计时。"""
        with self._lock:
            deadline = self.get(deadline_id)
            if deadline.status is not DeadlineStatus.RUNNING:
                raise DeadlineStateError("只有进行中的期限才能暂停")
            deadline.status = DeadlineStatus.PAUSED
            deadline.paused_at = self._clock.now()
            deadline.pause_reason = reason or None
            return deadline

    def resume(self, deadline_id: str) -> Deadline:
        """服务恢复：继续原有倒计时，剩余期限与暂停前一致。"""
        with self._lock:
            deadline = self.get(deadline_id)
            if deadline.status is not DeadlineStatus.PAUSED:
                raise DeadlineStateError("只有已暂停的期限才能恢复")
            now = self._clock.now()
            deadline.accumulated_pause += now - ensure_aware(deadline.paused_at, "paused_at")
            deadline.paused_at = None
            deadline.status = DeadlineStatus.RUNNING
            return deadline

    def complete(self, deadline_id: str) -> Deadline:
        return self._close(deadline_id, DeadlineStatus.COMPLETED)

    def cancel(self, deadline_id: str) -> Deadline:
        return self._close(deadline_id, DeadlineStatus.CANCELLED)

    def _close(self, deadline_id: str, status: DeadlineStatus) -> Deadline:
        with self._lock:
            deadline = self.get(deadline_id)
            if deadline.status not in _ACTIVE_STATUSES:
                raise DeadlineStateError("期限已结束，不能重复操作")
            deadline.status = status
            deadline.closed_at = self._clock.now()
            if deadline.paused_at is not None:
                deadline.accumulated_pause += deadline.closed_at - deadline.paused_at
                deadline.paused_at = None
            return deadline

    def remaining(self, deadline_id: str) -> timedelta:
        deadline = self.get(deadline_id)
        return deadline.remaining(self._clock.now())

    def is_expired(self, deadline_id: str) -> bool:
        deadline = self.get(deadline_id)
        return deadline.is_expired(self._clock.now())

    def expired(self, case_id: str | None = None) -> list[Deadline]:
        now = self._clock.now()
        return [
            deadline
            for deadline in self.for_case(case_id)
            if deadline.is_expired(now)
        ]

    def for_case(self, case_id: str | None = None) -> list[Deadline]:
        with self._lock:
            deadlines = list(self._deadlines.values())
        if case_id is None:
            return deadlines
        return [deadline for deadline in deadlines if deadline.case_id == case_id]
