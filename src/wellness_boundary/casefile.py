"""疗愈服务合规边界案卷聚合。

把经营主体与资质、服务包版本、宣传主张及证据、价格构成、知情确认、
风险筛查、服务记录、转介提示、合同变更和争议材料登记到同一案卷；
每个事实都发射符合交换契约的事件，形成可追溯的完整证据链。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping

from .claims import Claim, ClaimDesk
from .clock import Clock
from .complaints import ComplaintCase, ComplaintDesk, ComplaintFingerprint
from .consent import Consent, ConsentLedger, EvidenceItem, EvidenceVault
from .deadlines import DeadlineEngine, DeadlineKind
from .events import make_event
from .funds import FundsLedger, FundsOperation
from .offers import OfferCatalog, OfferPackage
from .records import ContractChange, ReferralHint, RiskScreening, ServiceRecord
from .registry import BusinessEntity, Registry
from .responsibility import Obligation, ResponsibilityChain


@dataclass(frozen=True)
class Disposition:
    """最终处理决定：固定当时有效的规则版本与完整证据链。"""

    outcome: str
    rule_version: str
    decided_at: datetime
    evidence_hashes: tuple[str, ...]


class CaseFile:
    def __init__(self, case_id: str, registry: Registry, clock: Clock, rule_version: str) -> None:
        if not rule_version or not rule_version.strip():
            raise ValueError("案卷必须登记当前有效的规则版本")
        self.case_id = case_id
        self.registry = registry
        self.clock = clock
        self.rule_version = rule_version
        self.claims = ClaimDesk(registry)
        self.consents = ConsentLedger()
        self.vault = EvidenceVault(self.consents)
        self.obligations = ResponsibilityChain()
        self.complaints = ComplaintDesk()
        self.funds = FundsLedger()
        self.deadlines = DeadlineEngine(clock)
        self.offers = OfferCatalog()
        self.lead_obligor: str | None = None
        self.screenings: list[RiskScreening] = []
        self.service_records: list[ServiceRecord] = []
        self.referrals: list[ReferralHint] = []
        self.contract_changes: list[ContractChange] = []
        self.disposition: Disposition | None = None
        self.events: list[dict[str, Any]] = []
        self._versions: dict[tuple[str, str], int] = {}
        self._regions: set[str] = set()
        self._parties: set[str] = set()
        self._opened = False

    # -- 事件 ----------------------------------------------------------------

    def _emit(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        key = (aggregate_type, aggregate_id)
        version = self._versions.get(key, 0) + 1
        self._versions[key] = version
        event = make_event(
            event_id=f"{self.case_id}-evt-{len(self.events) + 1:04d}",
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            occurred_at=self.clock.now(),
            version=version,
            payload=payload,
        )
        self.events.append(event)
        return event

    # -- 主体与案卷 ------------------------------------------------------------

    @property
    def regions(self) -> list[str]:
        """案件跨越的地区，来自各登记主体。"""
        return sorted(self._regions)

    @property
    def parties(self) -> list[str]:
        return sorted(self._parties)

    def register_party(self, entity_id: str) -> BusinessEntity:
        """登记涉案经营主体；跨地区订单由此汇总地区范围。"""
        entity = self.registry.entity(entity_id)
        self._parties.add(entity.entity_id)
        self._regions.update(entity.regions)
        return entity

    def open(
        self,
        lead_obligor: str,
        contract_snapshot: Mapping[str, Any],
        evidence_hashes: tuple[str, ...] = (),
    ) -> None:
        if self._opened:
            raise ValueError("案卷已开立，不能重复开立")
        self.register_party(lead_obligor)
        self.lead_obligor = lead_obligor
        self._opened = True
        self._emit("CASE_OPENED", "consumer_case", self.case_id, {
            "contract_snapshot": dict(contract_snapshot),
            "evidence_hashes": list(evidence_hashes),
            "lead_obligor": lead_obligor,
        })

    # -- 服务包版本 ------------------------------------------------------------

    def publish_offer(self, package: OfferPackage) -> OfferPackage:
        published = self.offers.publish(package)
        self._emit("OFFER_VERSIONED", "wellness_offer", package.offer_id, {
            "version": package.version,
            "provider_ref": package.provider_ref,
            "category": package.category.value,
            "price": [{"item": c.item, "amount_cents": c.amount_cents} for c in package.price],
            "total_cents": package.total_cents,
        })
        return published

    # -- 宣传审查 --------------------------------------------------------------

    def submit_claim(self, claim: Claim) -> Claim:
        return self.claims.submit(claim)

    def confirm_listing(self, claim_id: str, reviewer_id: str) -> Claim:
        claim = self.claims.confirm_listing(claim_id, reviewer_id, self.clock.now())
        self._emit("CLAIM_SCREENED", "marketing_claim", claim_id, {
            "review_scope": "listing",
            "rule_version": self.rule_version,
            "reviewer_ref": reviewer_id,
            "result": "listing_confirmed",
        })
        return claim

    def review_boundary(
        self,
        claim_id: str,
        reviewer_id: str,
        approve: bool,
        rule_version: str | None = None,
    ) -> Claim:
        effective_rules = rule_version or self.rule_version
        claim = self.claims.review_boundary(claim_id, reviewer_id, approve, effective_rules, self.clock.now())
        self._emit("CLAIM_SCREENED", "marketing_claim", claim_id, {
            "review_scope": "risk_boundary",
            "rule_version": effective_rules,
            "reviewer_ref": reviewer_id,
            "decision": "approved" if approve else "rejected",
            "exceeds_license": self.claims.exceeds_license(claim_id, self.clock.now()),
        })
        return claim

    # -- 知情同意与证据 ----------------------------------------------------------

    def record_consent(self, consent: Consent) -> Consent:
        recorded = self.consents.record(consent)
        self._emit("CONSENT_RECORDED", "consent", consent.consent_id, {
            "consumer_ref": consent.consumer_ref,
            "scopes": sorted(consent.scopes),
        })
        return recorded

    def withdraw_consent(self, consent_id: str) -> Consent:
        consent = self.consents.withdraw(consent_id, self.clock.now())
        self._emit("CONSENT_WITHDRAWN", "consent", consent_id, {
            "consent_ref": consent_id,
            "consumer_ref": consent.consumer_ref,
        })
        return consent

    def add_evidence(self, item: EvidenceItem) -> EvidenceItem:
        return self.vault.deposit(item)

    # -- 登记项 ----------------------------------------------------------------

    def record_screening(self, screening: RiskScreening) -> None:
        self.screenings.append(screening)

    def add_service_record(self, record: ServiceRecord) -> None:
        self.service_records.append(record)

    def add_referral(self, hint: ReferralHint) -> None:
        self.referrals.append(hint)

    def add_contract_change(self, change: ContractChange) -> None:
        self.contract_changes.append(change)

    # -- 投诉 ------------------------------------------------------------------

    def file_complaint(self, complaint_no: str, fingerprint: ComplaintFingerprint) -> ComplaintCase:
        case, outcome = self.complaints.file(complaint_no, fingerprint, self.clock.now())
        if outcome == "duplicate":
            return case  # 重复投诉沿用原回执，不产生新事件
        event_type = "COMPLAINT_SPLIT" if outcome == "split" else "COMPLAINT_RECEIPTED"
        payload: dict[str, Any] = {
            "complaint_no": complaint_no,
            "receipt_no": case.receipt_no,
            "fingerprint": {
                "contract_ref": fingerprint.contract_ref,
                "amount_cents": fingerprint.amount_cents,
                "material_hash": fingerprint.material_hash,
            },
        }
        if case.linked_to is not None:
            payload["linked_to"] = case.linked_to
        self._emit(event_type, "complaint", case.receipt_no, payload)
        return case

    # -- 责任链 ----------------------------------------------------------------

    def assign_obligation(self, obligation: Obligation) -> Obligation:
        return self.obligations.assign(obligation)

    def subcontract(self, obligation_id: str, performer_ref: str) -> Obligation:
        obligation = self.obligations.subcontract(obligation_id, performer_ref)
        self.register_party(performer_ref)  # 履约方进入案件范围，责任仍归原责任方
        return obligation

    def fulfill_obligation(self, obligation_id: str, by_party: str) -> Obligation:
        obligation = self.obligations.fulfill(obligation_id, by_party)
        self._emit("OBLIGATION_FULFILLED", "consumer_case", self.case_id, {
            "obligation_ref": obligation_id,
            "obligor_ref": obligation.obligor_ref,
            "fulfilled_by": by_party,
        })
        return obligation

    # -- 资金 ------------------------------------------------------------------

    def record_payment(self, order_ref: str, amount_cents: int) -> None:
        self.funds.record_payment(order_ref, amount_cents)

    def record_deposit(self, obligor_ref: str, amount_cents: int) -> None:
        self.funds.record_deposit(obligor_ref, amount_cents)

    def freeze(self, order_ref: str, amount_cents: int, idempotency_key: str) -> FundsOperation:
        op = self.funds.freeze(order_ref, amount_cents, idempotency_key, self.clock.now())
        self._emit("FUNDS_HELD", "payment", order_ref, {
            "order_ref": order_ref,
            "amount_cents": op.amount_cents,
            "idempotency_key": op.idempotency_key,
        })
        return op

    def refund(self, order_ref: str, obligor_ref: str, amount_cents: int, idempotency_key: str) -> FundsOperation:
        op = self.funds.refund(order_ref, amount_cents, idempotency_key, self.clock.now())
        self._emit("REFUND_ISSUED", "payment", order_ref, {
            "order_ref": order_ref,
            "amount_cents": op.amount_cents,
            "idempotency_key": op.idempotency_key,
        })
        self._emit("REMEDY_EXECUTED", "consumer_case", self.case_id, {
            "obligor_ref": obligor_ref,
            "amount": op.amount_cents,
        })
        return op

    def deduct_deposit(self, obligor_ref: str, amount_cents: int, idempotency_key: str) -> FundsOperation:
        op = self.funds.deduct_deposit(obligor_ref, amount_cents, idempotency_key, self.clock.now())
        self._emit("DEPOSIT_DEDUCTED", "payment", obligor_ref, {
            "obligor_ref": obligor_ref,
            "amount_cents": op.amount_cents,
            "idempotency_key": op.idempotency_key,
        })
        return op

    # -- 期限 ------------------------------------------------------------------

    def start_deadline(self, kind: DeadlineKind, duration: timedelta) -> None:
        self.deadlines.start(self.case_id, kind, duration)

    def pause_deadline(self, kind: DeadlineKind) -> None:
        self.deadlines.pause(self.case_id, kind)
        self._emit("DEADLINE_PAUSED", "consumer_case", self.case_id, {
            "case_ref": self.case_id,
            "deadline_kind": kind.value,
        })

    def resume_deadline(self, kind: DeadlineKind) -> None:
        self.deadlines.resume(self.case_id, kind)
        self._emit("DEADLINE_RESUMED", "consumer_case", self.case_id, {
            "case_ref": self.case_id,
            "deadline_kind": kind.value,
        })

    # -- 最终处理 ----------------------------------------------------------------

    def update_rule_version(self, rule_version: str) -> None:
        """规则演进；已作出的处理决定仍追溯当时有效的版本。"""
        if not rule_version or not rule_version.strip():
            raise ValueError("规则版本不能为空")
        self.rule_version = rule_version

    def record_disposition(self, outcome: str) -> Disposition:
        if self.disposition is not None:
            raise ValueError("最终处理只能记录一次")
        if not outcome or not outcome.strip():
            raise ValueError("处理结论不能为空")
        self.disposition = Disposition(
            outcome=outcome,
            rule_version=self.rule_version,
            decided_at=self.clock.now(),
            evidence_hashes=tuple(self.vault.hashes()),
        )
        self._emit("DISPOSITION_RECORDED", "consumer_case", self.case_id, {
            "outcome": outcome,
            "rule_version": self.disposition.rule_version,
            "evidence_hashes": list(self.disposition.evidence_hashes),
        })
        return self.disposition
