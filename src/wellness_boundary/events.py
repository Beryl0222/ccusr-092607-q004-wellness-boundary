"""由领域事实生成符合交换契约的事件信封。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from .clock import require_aware


def make_event(
    event_id: str,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    occurred_at: datetime,
    version: int,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """构造事件信封；occurred_at 必须携带时区，version 从 1 开始递增。"""
    require_aware(occurred_at, "事件发生时间")
    if version < 1:
        raise ValueError("版本号必须从 1 开始")
    return {
        "event_id": event_id,
        "event_type": event_type,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "occurred_at": occurred_at.isoformat(),
        "version": version,
        "payload": dict(payload),
    }
