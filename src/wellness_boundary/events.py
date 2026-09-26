"""事件日志：契约校验、业务幂等、冲突隔离与版本推进。

契约层（``contracts.validate_event``）只定义可稳定交换的基础事实；
本模块承担领域约定中交给上层服务的三件事：

- 相同事件标识且内容一致的重投视为幂等重放，直接返回已登记事件；
- 相同事件标识但内容不同的提交被拒绝（冲突隔离），不覆盖既有事实；
- 同一聚合的事件版本号必须严格递增（状态推进），保证审计链无回退。
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping

from .clock import to_iso
from .contracts import ContractIssue
from .errors import ContractViolationError, EventConflictError

EventValidator = Callable[[Mapping[str, Any]], Iterable[ContractIssue]]


def _fingerprint(event: Mapping[str, Any]) -> str:
    """对事件身份字段做规范化摘要，用于幂等判定。"""
    canonical = json.dumps(
        {
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "aggregate_type": event.get("aggregate_type"),
            "aggregate_id": event.get("aggregate_id"),
            "occurred_at": event.get("occurred_at"),
            "payload": event.get("payload"),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class EventLog:
    """单个案卷范围内的事件日志。"""

    def __init__(self, validator: EventValidator | None = None) -> None:
        self._validator = validator
        self._events: list[dict[str, Any]] = []
        self._by_id: dict[str, dict[str, Any]] = {}
        self._fingerprints: dict[str, str] = {}
        self._versions: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()

    def record(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        occurred_at: datetime,
        payload: Mapping[str, Any],
        event_id: str | None = None,
    ) -> dict[str, Any]:
        """登记一条事件，返回已登记的事件信封。

        ``event_id`` 缺省时按聚合与版本号生成；外部系统重投时应携带原标识。
        """
        occurred_iso = to_iso(occurred_at)
        with self._lock:
            if event_id is not None and event_id in self._by_id:
                existing = self._by_id[event_id]
                candidate = {
                    "event_id": event_id,
                    "event_type": event_type,
                    "aggregate_type": aggregate_type,
                    "aggregate_id": aggregate_id,
                    "occurred_at": occurred_iso,
                    "payload": dict(payload),
                }
                if self._fingerprints[event_id] != _fingerprint(candidate):
                    raise EventConflictError(f"事件 {event_id} 已登记且内容不一致")
                return existing
            key = (aggregate_type, aggregate_id)
            version = self._versions.get(key, 0) + 1
            event = {
                "event_id": event_id or f"{aggregate_type}:{aggregate_id}:{version}",
                "event_type": event_type,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "occurred_at": occurred_iso,
                "version": version,
                "payload": dict(payload),
            }
            if self._validator is not None:
                issues = list(self._validator(event))
                if issues:
                    detail = "；".join(f"{issue.field}:{issue.code}" for issue in issues)
                    raise ContractViolationError(f"事件不满足交换契约：{detail}")
            self._events.append(event)
            self._by_id[event["event_id"]] = event
            self._fingerprints[event["event_id"]] = _fingerprint(event)
            self._versions[key] = version
            return event

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(event) for event in self._events]

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)
