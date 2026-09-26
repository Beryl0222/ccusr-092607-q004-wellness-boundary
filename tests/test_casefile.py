import unittest
from datetime import timedelta

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import T0, make_casebook, make_chain, make_complaint, make_parties

from wellness_boundary import (
    CaseStatus,
    ConsentRecord,
    ContractChange,
    Disposition,
    DisputeMaterial,
    Obligation,
    ObligationKind,
    ObligationStatus,
    OfferVersion,
    PriceBreakdown,
    PriceItem,
    ReferralNotice,
    RiskScreening,
    RuleBook,
    RuleSet,
    ServiceRecord,
    ServiceRecordStatus,
)
from wellness_boundary.errors import (
    ConsentWithdrawnError,
    DispositionStateError,
    DomainError,
    DuplicateRegistrationError,
    ObligationStateError,
    RuleVersionError,
)
from decimal import Decimal


def make_case():
    casebook, clock = make_casebook()
    case = casebook.open_case(
        make_complaint(),
        fingerprint="fp",
        chain=make_chain(),
        parties=make_parties(),
    )
    return casebook, clock, case


def make_consent(consent_id="consent-1", scope="service_delivery"):
    return ConsentRecord(
        consent_id=consent_id,
        consumer_id="consumer-1",
        scope=scope,
        granted_at=T0,
    )


class RegistrationTests(unittest.TestCase):
    def test_open_case_emits_contract_event(self) -> None:
        _, _, case = make_case()
        (event,) = [e for e in case.events.all() if e["event_type"] == "CASE_OPENED"]
        self.assertEqual("hash-contract-001", event["payload"]["contract_snapshot"])
        self.assertEqual(["mat-fp-1", "mat-fp-2"], event["payload"]["evidence_hashes"])
        self.assertEqual(1, event["version"])

    def test_offer_versioning_and_duplicate_guard(self) -> None:
        _, clock, case = make_case()
        offer = OfferVersion(
            offer_id="offer-1",
            version=1,
            title="七日禅修旅修营",
            service_items=("住宿", "冥想课"),
            price=PriceBreakdown("CNY", (PriceItem("课程", Decimal("1000")), PriceItem("住宿", Decimal("280")))),
            effective_from=T0,
        )
        event = case.register_offer_version(offer, clock.now())
        self.assertEqual("OFFER_VERSIONED", event["event_type"])
        self.assertEqual("1280", event["payload"]["price_total"])
        with self.assertRaises(DuplicateRegistrationError):
            case.register_offer_version(offer, clock.now())

    def test_screening_referral_and_contract_change_register(self) -> None:
        _, clock, case = make_case()
        case.register_screening(RiskScreening("scr-1", "consumer-1", "needs_referral", "prof-1", T0))
        case.register_referral(ReferralNotice("ref-1", "consumer-1", "筛查提示抑郁风险", "三甲医院心理科", T0))
        case.register_contract_change(ContractChange("chg-1", "contract-1", "hash-a", "hash-b", "补签退款条款", T0))
        self.assertEqual("needs_referral", case.screenings[0].result)
        self.assertEqual("hash-b", case.contract_changes[0].after_hash)


class ConsentWithdrawalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.casebook, self.clock, self.case = make_case()
        self.case.record_consent(make_consent(), self.clock.now())
        self.case.record_consent(make_consent("consent-2", "marketing"), self.clock.now())
        self.case.add_service_record(
            ServiceRecord("rec-delivered", "consumer-1", "mer-001", "consent-1", T0, status=ServiceRecordStatus.DELIVERED)
        )
        self.case.add_service_record(
            ServiceRecord("rec-future", "consumer-1", "mer-001", "consent-1", T0 + timedelta(days=3))
        )
        self.case.register_material(
            DisputeMaterial("mat-1", "consumer-1", "screenshot", "sha-1", "dispute", "consumer-1", T0)
        )

    def test_withdrawal_stops_future_service_and_restricts_retained(self) -> None:
        self.case.withdraw_consent("consent-1", self.clock.now())
        records = self.case.service_records
        self.assertEqual(ServiceRecordStatus.CANCELLED, records["rec-future"].status)  # 停止未来服务
        self.assertTrue(records["rec-delivered"].access_restricted)  # 既有履约保留并限制访问
        self.assertEqual(ServiceRecordStatus.DELIVERED, records["rec-delivered"].status)  # 依法保留
        self.assertTrue(self.case.materials["mat-1"].access_restricted)  # 争议证据限制访问

    def test_withdrawal_blocks_new_service_and_new_purpose(self) -> None:
        self.case.withdraw_consent("consent-1", self.clock.now())
        self.case.withdraw_consent("consent-2", self.clock.now())
        with self.assertRaises(ConsentWithdrawnError):
            self.case.add_service_record(
                ServiceRecord("rec-new", "consumer-1", "mer-001", "consent-1", T0)
            )
        with self.assertRaises(ConsentWithdrawnError):
            self.case.register_material(
                DisputeMaterial("mat-2", "consumer-1", "profiling", "sha-2", "marketing", "mer-001", T0)
            )
        # 争议与履约材料依法保留，不受撤回影响
        self.case.register_material(
            DisputeMaterial("mat-3", "consumer-1", "recording", "sha-3", "dispute", "consumer-1", T0)
        )
        self.assertIn("mat-3", self.case.materials)

    def test_double_withdrawal_rejected(self) -> None:
        self.case.withdraw_consent("consent-1", self.clock.now())
        with self.assertRaises(ConsentWithdrawnError):
            self.case.withdraw_consent("consent-1", self.clock.now())

    def test_withdrawal_emits_contract_event(self) -> None:
        self.case.withdraw_consent("consent-1", self.clock.now())
        events = [e for e in self.case.events.all() if e["event_type"] == "CONSENT_RECORDED"]
        self.assertEqual(["granted", "granted", "withdrawn"], [e["payload"]["action"] for e in events])


class ObligationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.casebook, self.clock, self.case = make_case()
        self.case.assign_obligation(
            Obligation("ob-1", self.case.case_id, ObligationKind.REFUND, "mer-001", "退还课程费用", T0)
        )

    def test_delegation_keeps_original_obligor(self) -> None:
        obligation = self.case.delegate_obligation("ob-1", "sub-001", self.clock.now())
        self.assertEqual("sub-001", obligation.delegated_to)
        self.assertEqual("mer-001", obligation.obligor_ref)  # 责任不因转包而丢失
        self.assertEqual(ObligationStatus.PENDING, obligation.status)

    def test_delegate_requires_registered_party(self) -> None:
        with self.assertRaises(DomainError):
            self.case.delegate_obligation("ob-1", "ghost-001", self.clock.now())

    def test_assign_requires_registered_obligor(self) -> None:
        with self.assertRaises(DomainError):
            self.case.assign_obligation(
                Obligation("ob-2", self.case.case_id, ObligationKind.RECTIFICATION, "ghost-001", "整改", T0)
            )

    def test_fulfilled_obligation_cannot_be_delegated_or_refulfilled(self) -> None:
        self.case.fulfill_obligation("ob-1", self.clock.now())
        with self.assertRaises(ObligationStateError):
            self.case.delegate_obligation("ob-1", "sub-001", self.clock.now())
        with self.assertRaises(ObligationStateError):
            self.case.fulfill_obligation("ob-1", self.clock.now())
        self.assertEqual([], self.case.outstanding_obligations())


class DispositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.casebook, self.clock, self.case = make_case()
        self.rulebook = RuleBook()
        self.rulebook.register(
            RuleSet("RB-2026-06", T0 - timedelta(days=100), T0 - timedelta(days=10), "旧版规则")
        )
        self.rulebook.register(
            RuleSet("RB-2026-09", T0 - timedelta(days=10), None, "现行规则", ("宣传不得越界",))
        )

    def test_dispose_requires_effective_rule_version(self) -> None:
        with self.assertRaises(RuleVersionError):
            self.case.dispose(
                Disposition("disp-1", self.clock.now(), "RB-2026-06", "按旧版处理", "监管员甲"),
                self.rulebook,
            )
        self.case.dispose(
            Disposition("disp-1", self.clock.now(), "RB-2026-09", "按现行规则处理", "监管员甲"),
            self.rulebook,
        )
        self.assertEqual(CaseStatus.DISPOSED, self.case.status)

    def test_double_disposition_rejected(self) -> None:
        self.case.dispose(
            Disposition("disp-1", self.clock.now(), "RB-2026-09", "处理", "监管员甲"),
            self.rulebook,
        )
        with self.assertRaises(DispositionStateError):
            self.case.dispose(
                Disposition("disp-2", self.clock.now(), "RB-2026-09", "再处理", "监管员乙"),
                self.rulebook,
            )


if __name__ == "__main__":
    unittest.main()
