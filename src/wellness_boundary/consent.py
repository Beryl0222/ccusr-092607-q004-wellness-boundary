"""知情确认、同意撤回与证据访问限制。

消费者撤回同意后停止未来服务与新用途；
既有履约和争议证据依法保留，并只允许限定目的访问。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .clock import require_aware


class Purpose(Enum):
    FULFILLMENT = "fulfillment"      # 既有履约
    DISPUTE = "dispute"              # 争议处理
    REGULATORY = "regulatory"        # 监管调取
    NEW_SERVICE = "new_service"      # 未来服务
    MARKETING = "marketing"          # 新用途


#: 撤回后仍被法律允许访问证据的目的。
RETAINED_PURPOSES = frozenset({Purpose.FULFILLMENT, Purpose.DISPUTE, Purpose.REGULATORY})


@dataclass
class Consent:
    """一次知情确认，记录授权范围与撤回时间。"""

    consent_id: str
    consumer_ref: str
    scopes: frozenset[str]
    granted_at: datetime
    withdrawn_at: datetime | None = None

    def __post_init__(self) -> None:
        require_aware(self.granted_at, "同意时间")
        if self.withdrawn_at is not None:
            require_aware(self.withdrawn_at, "撤回时间")

    def allows(self, scope: str, at: datetime) -> bool:
        require_aware(at, "判断时点")
        if scope not in self.scopes or at < self.granted_at:
            return False
        return self.withdrawn_at is None or at < self.withdrawn_at


class ConsentLedger:
    def __init__(self) -> None:
        self._consents: dict[str, Consent] = {}

    def record(self, consent: Consent) -> Consent:
        if consent.consent_id in self._consents:
            raise ValueError(f"知情确认已登记: {consent.consent_id}")
        self._consents[consent.consent_id] = consent
        return consent

    def get(self, consent_id: str) -> Consent:
        try:
            return self._consents[consent_id]
        except KeyError:
            raise KeyError(f"知情确认未登记: {consent_id}") from None

    def withdraw(self, consent_id: str, at: datetime) -> Consent:
        """撤回同意：停止未来服务与新用途，已发生的授权不受影响。"""
        require_aware(at, "撤回时间")
        consent = self.get(consent_id)
        if consent.withdrawn_at is not None:
            raise ValueError("同意已撤回，不能重复撤回")
        if at < consent.granted_at:
            raise ValueError("撤回时间不能早于同意时间")
        consent.withdrawn_at = at
        return consent

    def permits(self, consent_id: str, scope: str, at: datetime) -> bool:
        return self.get(consent_id).allows(scope, at)


@dataclass
class EvidenceItem:
    """一份履约或争议证据，登记来源同意与采集时间。"""

    evidence_hash: str
    consent_ref: str
    collected_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.collected_at, "证据采集时间")


class EvidenceVault:
    """证据库：撤回后证据仍然保留，但访问目的受到限制。"""

    def __init__(self, ledger: ConsentLedger) -> None:
        self._ledger = ledger
        self._items: dict[str, EvidenceItem] = {}

    def deposit(self, item: EvidenceItem) -> EvidenceItem:
        if item.evidence_hash in self._items:
            raise ValueError(f"证据已登记: {item.evidence_hash}")
        consent = self._ledger.get(item.consent_ref)
        if item.collected_at < consent.granted_at:
            raise ValueError("证据采集时间不能早于同意时间")
        self._items[item.evidence_hash] = item
        return item

    def is_restricted(self, evidence_hash: str, at: datetime) -> bool:
        item = self._items[evidence_hash]
        consent = self._ledger.get(item.consent_ref)
        return consent.withdrawn_at is not None and at >= consent.withdrawn_at

    def access(self, evidence_hash: str, purpose: Purpose, at: datetime) -> EvidenceItem:
        """按目的访问证据；撤回后仅限履约、争议与监管目的。"""
        require_aware(at, "访问时间")
        try:
            item = self._items[evidence_hash]
        except KeyError:
            raise KeyError(f"证据未登记: {evidence_hash}") from None
        if self.is_restricted(evidence_hash, at) and purpose not in RETAINED_PURPOSES:
            raise PermissionError("同意已撤回，证据仅可因履约、争议或监管目的访问")
        return item

    def hashes(self) -> list[str]:
        return sorted(self._items)
