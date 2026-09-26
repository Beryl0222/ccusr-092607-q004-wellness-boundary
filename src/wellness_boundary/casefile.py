"""案卷聚合与案卷库。

``CaseFile`` 登记一单争议的全部材料：经营主体与从业资质、服务包版本、宣传
主张及证据、价格构成、知情确认、风险筛查、服务记录、转介提示、合同变更和
争议材料，并承载三条核心规则：

- 消费者撤回同意后停止未来服务与新用途，既有履约和争议证据依法保留并限制访问；
- 义务可以转包执行，但责任方（``obligor_ref``）不因转包而丢失；
- 最终处理必须引用作出时点有效的规则版本。

``CaseBook`` 负责开案、期限引擎与资金台账的接线，并在状态推进时登记契约事件。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Iterable

from .catalog import MarketingClaim, OfferVersion, ProviderProfile
from .clock import Clock, ensure_aware
from .complaints import Complaint
from .deadlines import Deadline, DeadlineEngine, DeadlineKind
from .errors import (
    CaseNotFoundError,
    ClaimNotFoundError,
    ConsentNotFoundError,
    ConsentWithdrawnError,
    DispositionStateError,
    DuplicateRegistrationError,
    DomainError,
    ObligationNotFoundError,
    ObligationStateError,
    RuleVersionError,
)
from .events import EventLog, EventValidator
from .records import (
    RETAINED_PURPOSES,
    ConsentRecord,
    ConsentStatus,
    ContractChange,
    DisputeMaterial,
    ReferralNotice,
    RiskScreening,
    ServiceRecord,
    ServiceRecordStatus,
)
from .remedies import RemedyLedger, RemedyOperation, RemedyRecord
from .rules import RuleBook


class PartyRole(str, Enum):
    SELLER = "seller"  # 销售方（面向消费者的责任方）
    PLATFORM = "platform"  # 平台
    SUBCONTRACTOR = "subcontractor"  # 履约分包方


@dataclass(frozen=True)
class ChainLink:
    """责任链一环：一次订单可跨多个地区和多个经营方。"""

    party_ref: str
    role: PartyRole
    region: str


class CaseStatus(str, Enum):
    OPEN = "open"
    DISPOSED = "disposed"  # 已作出最终处理


class ObligationKind(str, Enum):
    REFUND = "refund"
    RECTIFICATION = "rectification"
    EVIDENCE_SUPPLEMENT = "evidence_supplement"
    DISCLOSURE = "disclosure"
    SERVICE_STOP = "service_stop"


class ObligationStatus(str, Enum):
    PENDING = "pending"
    FULFILLED = "fulfilled"


@dataclass
class Obligation:
    """当事方义务；``delegated_to`` 只记录执行转包，责任仍在 ``obligor_ref``。"""

    obligation_id: str
    case_id: str
    kind: ObligationKind
    obligor_ref: str
    description: str
    created_at: datetime
    deadline_id: str | None = None
    delegated_to: str | None = None
    status: ObligationStatus = ObligationStatus.PENDING
    fulfilled_at: datetime | None = None


@dataclass(frozen=True)
class Disposition:
    """最终处理。"""

    disposition_id: str
    decided_at: datetime
    rule_version: str
    summary: str
    decided_by: str


@dataclass
class CaseFile:
    case_id: str
    complaint_no: str
    receipt_no: str
    consumer_id: str
    order_ref: str
    fingerprint: str
    opened_at: datetime
    chain: list[ChainLink] = field(default_factory=list)
    status: CaseStatus = CaseStatus.OPEN
    duplicate_filings: int = 0
    parties: dict[str, ProviderProfile] = field(default_factory=dict)
    offers: dict[tuple[str, int], OfferVersion] = field(default_factory=dict)
    claims: dict[str, MarketingClaim] = field(default_factory=dict)
    consents: dict[str, ConsentRecord] = field(default_factory=dict)
    service_records: dict[str, ServiceRecord] = field(default_factory=dict)
    screenings: list[RiskScreening] = field(default_factory=list)
    referrals: list[ReferralNotice] = field(default_factory=list)
    contract_changes: list[ContractChange] = field(default_factory=list)
    materials: dict[str, DisputeMaterial] = field(default_factory=dict)
    obligations: dict[str, Obligation] = field(default_factory=dict)
    disposition: Disposition | None = None
    events: EventLog = field(default_factory=EventLog)

    # ---- 登记：主体、服务包、宣传 ----

    def register_party(self, profile: ProviderProfile) -> None:
        self.parties[profile.provider_ref] = profile

    def register_offer_version(self, offer: OfferVersion, occurred_at: datetime) -> dict:
        key = (offer.offer_id, offer.version)
        if key in self.offers:
            raise DuplicateRegistrationError(f"服务包版本已登记：{offer.offer_id}@{offer.version}")
        self.offers[key] = offer
        return self.events.record(
            "OFFER_VERSIONED",
            "wellness_offer",
            f"{offer.offer_id}@{offer.version}",
            occurred_at,
            {
                "offer_id": offer.offer_id,
                "version": offer.version,
                "title": offer.title,
                "price_total": str(offer.price.total),
                "currency": offer.price.currency,
            },
        )

    def register_claim(self, claim: MarketingClaim) -> None:
        if claim.claim_id in self.claims:
            raise DuplicateRegistrationError(f"宣传主张已登记：{claim.claim_id}")
        self.claims[claim.claim_id] = claim

    def claim_of(self, claim_id: str) -> MarketingClaim:
        try:
            return self.claims[claim_id]
        except KeyError:
            raise ClaimNotFoundError(f"宣传主张不存在：{claim_id}") from None

    # ---- 知情确认与撤回 ----

    def record_consent(self, consent: ConsentRecord, occurred_at: datetime) -> dict:
        if consent.consent_id in self.consents:
            raise DuplicateRegistrationError(f"知情确认已登记：{consent.consent_id}")
        self.consents[consent.consent_id] = consent
        return self.events.record(
            "CONSENT_RECORDED",
            "consumer_case",
            self.case_id,
            occurred_at,
            {
                "action": "granted",
                "consent_id": consent.consent_id,
                "consumer_id": consent.consumer_id,
                "scope": consent.scope,
            },
        )

    def withdraw_consent(self, consent_id: str, now: datetime) -> dict:
        """撤回同意：停止未来服务与新用途，既有履约和争议证据保留并限制访问。"""
        ensure_aware(now)
        consent = self.consents.get(consent_id)
        if consent is None:
            raise ConsentNotFoundError(f"知情确认不存在：{consent_id}")
        if consent.status is ConsentStatus.WITHDRAWN:
            raise ConsentWithdrawnError("该同意已撤回")
        consent.status = ConsentStatus.WITHDRAWN
        consent.withdrawn_at = now
        for record in self.service_records.values():
            if record.consent_id == consent_id and record.status is ServiceRecordStatus.SCHEDULED:
                record.status = ServiceRecordStatus.CANCELLED  # 停止未来服务
            if record.consumer_id == consent.consumer_id and record.status is ServiceRecordStatus.DELIVERED:
                record.access_restricted = True  # 既有履约记录保留但限制访问
        for material in self.materials.values():
            if material.consumer_id == consent.consumer_id and material.purpose in RETAINED_PURPOSES:
                material.access_restricted = True  # 争议证据依法保留并限制访问
        return self.events.record(
            "CONSENT_RECORDED",
            "consumer_case",
            self.case_id,
            now,
            {
                "action": "withdrawn",
                "consent_id": consent.consent_id,
                "consumer_id": consent.consumer_id,
                "scope": consent.scope,
            },
        )

    def _active_consent(self, consumer_id: str, scope: str) -> ConsentRecord | None:
        for consent in self.consents.values():
            if (
                consent.consumer_id == consumer_id
                and consent.scope == scope
                and consent.status is ConsentStatus.ACTIVE
            ):
                return consent
        return None

    # ---- 服务记录 ----

    def add_service_record(self, record: ServiceRecord) -> None:
        if record.record_id in self.service_records:
            raise DuplicateRegistrationError(f"服务记录已登记：{record.record_id}")
        consent = self.consents.get(record.consent_id)
        if consent is None:
            raise ConsentNotFoundError(f"服务记录缺少对应知情确认：{record.consent_id}")
        if consent.status is ConsentStatus.WITHDRAWN:
            raise ConsentWithdrawnError("撤回同意后不得新增服务")
        self.service_records[record.record_id] = record

    # ---- 风险筛查 / 转介提示 / 合同变更 ----

    def register_screening(self, screening: RiskScreening) -> None:
        self.screenings.append(screening)

    def register_referral(self, notice: ReferralNotice) -> None:
        self.referrals.append(notice)

    def register_contract_change(self, change: ContractChange) -> None:
        self.contract_changes.append(change)

    # ---- 争议材料 ----

    def register_material(self, material: DisputeMaterial) -> None:
        if material.material_id in self.materials:
            raise DuplicateRegistrationError(f"争议材料已登记：{material.material_id}")
        if material.purpose not in RETAINED_PURPOSES:
            # 履约与争议之外的用途属于新用途，须持有有效同意
            if self._active_consent(material.consumer_id, material.purpose) is None:
                raise ConsentWithdrawnError("撤回同意后不得将材料用于新用途")
        self.materials[material.material_id] = material

    # ---- 义务与转包 ----

    def assign_obligation(self, obligation: Obligation) -> None:
        if obligation.obligation_id in self.obligations:
            raise DuplicateRegistrationError(f"义务已登记：{obligation.obligation_id}")
        if obligation.obligor_ref not in self.parties:
            raise DomainError(f"责任方未登记为案卷当事方：{obligation.obligor_ref}")
        self.obligations[obligation.obligation_id] = obligation

    def obligation_of(self, obligation_id: str) -> Obligation:
        try:
            return self.obligations[obligation_id]
        except KeyError:
            raise ObligationNotFoundError(f"义务不存在：{obligation_id}") from None

    def delegate_obligation(self, obligation_id: str, to_party: str, now: datetime) -> Obligation:
        """转包执行；责任方保持不变，责任不因转包而丢失。"""
        ensure_aware(now)
        obligation = self.obligation_of(obligation_id)
        if obligation.status is ObligationStatus.FULFILLED:
            raise ObligationStateError("义务已履行，不能再转包")
        if to_party not in self.parties:
            raise DomainError(f"转包对象未登记为案卷当事方：{to_party}")
        obligation.delegated_to = to_party
        return obligation

    def fulfill_obligation(self, obligation_id: str, now: datetime) -> Obligation:
        ensure_aware(now)
        obligation = self.obligation_of(obligation_id)
        if obligation.status is ObligationStatus.FULFILLED:
            raise ObligationStateError("义务已履行")
        obligation.status = ObligationStatus.FULFILLED
        obligation.fulfilled_at = now
        return obligation

    def outstanding_obligations(self) -> list[Obligation]:
        return [
            obligation
            for obligation in self.obligations.values()
            if obligation.status is ObligationStatus.PENDING
        ]

    # ---- 最终处理 ----

    def dispose(self, disposition: Disposition, rulebook: RuleBook) -> None:
        if self.disposition is not None:
            raise DispositionStateError("案卷已有最终处理")
        effective = rulebook.effective_at(disposition.decided_at)
        if effective.rule_version != disposition.rule_version:
            raise RuleVersionError(
                f"规则版本 {disposition.rule_version} 在处理时点并非有效版本"
                f"（当时有效：{effective.rule_version}）"
            )
        self.disposition = disposition
        self.status = CaseStatus.DISPOSED


class CaseBook:
    """案卷库：开案、期限引擎与资金台账的接线处。"""

    def __init__(self, clock: Clock, event_validator: EventValidator | None = None) -> None:
        self.clock = clock
        self.deadlines = DeadlineEngine(clock)
        self.remedies = RemedyLedger(clock)
        self._event_validator = event_validator
        self._cases: dict[str, CaseFile] = {}
        self._by_complaint: dict[str, list[str]] = {}
        self._case_seq = 0
        self._receipt_seq = 0
        self._lock = threading.Lock()

    def open_case(
        self,
        complaint: Complaint,
        *,
        fingerprint: str,
        chain: Iterable[ChainLink] = (),
        parties: Iterable[ProviderProfile] = (),
    ) -> CaseFile:
        with self._lock:
            self._case_seq += 1
            self._receipt_seq += 1
            case = CaseFile(
                case_id=f"CASE-{self._case_seq:06d}",
                complaint_no=complaint.complaint_no,
                receipt_no=f"RCPT-{self._receipt_seq:06d}",
                consumer_id=complaint.consumer_id,
                order_ref=complaint.order_ref,
                fingerprint=fingerprint,
                opened_at=self.clock.now(),
                chain=list(chain),
                events=EventLog(self._event_validator),
            )
            for profile in parties:
                case.register_party(profile)
            case.events.record(
                "CASE_OPENED",
                "consumer_case",
                case.case_id,
                self.clock.now(),
                {
                    "complaint_no": complaint.complaint_no,
                    "receipt_no": case.receipt_no,
                    "contract_snapshot": complaint.contract_snapshot_hash,
                    "evidence_hashes": sorted(complaint.material_fingerprints),
                    "amount": str(complaint.amount),
                    "currency": complaint.currency,
                    "fingerprint": fingerprint,
                },
            )
            self._cases[case.case_id] = case
            self._by_complaint.setdefault(complaint.complaint_no, []).append(case.case_id)
            return case

    def get(self, case_id: str) -> CaseFile:
        try:
            return self._cases[case_id]
        except KeyError:
            raise CaseNotFoundError(f"案卷不存在：{case_id}") from None

    def find_by_complaint_no(self, complaint_no: str) -> list[CaseFile]:
        return [self._cases[case_id] for case_id in self._by_complaint.get(complaint_no, [])]

    def open_deadline(self, case_id: str, kind: DeadlineKind, duration: timedelta) -> Deadline:
        self.get(case_id)
        return self.deadlines.open(case_id, kind, duration)

    def execute_remedy(self, operation: RemedyOperation) -> RemedyRecord:
        """执行资金操作并登记 REMEDY_EXECUTED；幂等重放不重复登记事件。"""
        case = self.get(operation.case_id)
        record = self.remedies.execute(operation)
        if not record.replayed:
            case.events.record(
                "REMEDY_EXECUTED",
                "consumer_case",
                case.case_id,
                record.applied_at,
                {
                    "kind": operation.kind.value,
                    "obligor_ref": operation.obligor_ref,
                    "amount": str(operation.amount),
                    "currency": operation.currency,
                    "idempotency_key": operation.idempotency_key,
                    "reason": operation.reason,
                },
            )
        return record
