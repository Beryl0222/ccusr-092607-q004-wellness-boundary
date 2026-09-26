"""案卷登记项：风险筛查、服务记录、转介提示与合同变更。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .clock import require_aware


@dataclass(frozen=True)
class RiskScreening:
    """服务前的风险筛查记录。"""

    screening_id: str
    consumer_ref: str
    outcome: str
    screened_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.screened_at, "筛查时间")


@dataclass(frozen=True)
class ServiceRecord:
    """一次实际服务的记录。"""

    record_id: str
    order_ref: str
    summary: str
    provided_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.provided_at, "服务时间")


@dataclass(frozen=True)
class ReferralHint:
    """发现超出服务边界时给出的转介提示。"""

    hint_id: str
    consumer_ref: str
    target: str
    reason: str
    hinted_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.hinted_at, "转介提示时间")


@dataclass(frozen=True)
class ContractChange:
    """合同变更记录。"""

    change_id: str
    contract_ref: str
    summary: str
    changed_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.changed_at, "合同变更时间")
