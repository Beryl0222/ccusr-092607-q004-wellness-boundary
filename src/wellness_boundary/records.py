"""案卷登记项：知情确认、服务记录、风险筛查、转介提示、合同变更与争议材料。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

#: 撤回同意后仍依法保留的争议材料用途；其余用途一律视为“新用途”被阻断。
PURPOSE_DISPUTE = "dispute"
PURPOSE_PERFORMANCE = "performance"
RETAINED_PURPOSES = frozenset({PURPOSE_DISPUTE, PURPOSE_PERFORMANCE})


class ConsentStatus(str, Enum):
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"


@dataclass
class ConsentRecord:
    """知情确认。"""

    consent_id: str
    consumer_id: str
    scope: str  # service_delivery / marketing / data_analysis ...
    granted_at: datetime
    version: int = 1
    status: ConsentStatus = ConsentStatus.ACTIVE
    withdrawn_at: datetime | None = None


class ServiceRecordStatus(str, Enum):
    SCHEDULED = "scheduled"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@dataclass
class ServiceRecord:
    """服务记录；撤回同意后未履约的一律取消，已履约的保留并限制访问。"""

    record_id: str
    consumer_id: str
    provider_ref: str
    consent_id: str
    scheduled_at: datetime
    summary: str = ""
    status: ServiceRecordStatus = ServiceRecordStatus.SCHEDULED
    access_restricted: bool = False


@dataclass(frozen=True)
class RiskScreening:
    """风险筛查。"""

    screening_id: str
    consumer_id: str
    result: str  # cleared / needs_referral / contraindicated
    screened_by: str
    screened_at: datetime
    notes: str = ""


@dataclass(frozen=True)
class ReferralNotice:
    """转介提示。"""

    notice_id: str
    consumer_id: str
    reason: str
    target: str
    issued_at: datetime


@dataclass(frozen=True)
class ContractChange:
    """合同变更：只登记前后指纹，不改写历史快照。"""

    change_id: str
    contract_ref: str
    before_hash: str
    after_hash: str
    reason: str
    changed_at: datetime


@dataclass
class DisputeMaterial:
    """争议材料。"""

    material_id: str
    consumer_id: str
    kind: str  # screenshot / recording / contract / receipt / chat_log
    sha256: str
    purpose: str  # dispute / performance 依法保留；其余视为新用途
    submitted_by: str
    submitted_at: datetime
    access_restricted: bool = False
