import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from support import T0, build_registry
from wellness_boundary.casefile import CaseFile
from wellness_boundary.claims import Claim, ClaimStatus
from wellness_boundary.clock import ManualClock
from wellness_boundary.complaints import ComplaintFingerprint
from wellness_boundary.consent import Consent, EvidenceItem
from wellness_boundary.contracts import validate_event
from wellness_boundary.deadlines import DeadlineKind, DeadlineStatus
from wellness_boundary.offers import OfferPackage, PriceComponent
from wellness_boundary.registry import ServiceCategory
from wellness_boundary.responsibility import Obligation

SCHEMA = json.loads((ROOT / "contracts/domain.schema.json").read_text(encoding="utf-8"))


def build_case() -> CaseFile:
    case = CaseFile("case-0001", build_registry(), ManualClock(T0), rule_version="rules-2026v1")
    case.open("merchant-1", {"contract_ref": "contract-1", "amount_cents": 680000})
    return case


class CaseFileTests(unittest.TestCase):
    def test_full_lifecycle_events_all_match_contract(self) -> None:
        case = build_case()
        case.publish_offer(OfferPackage(
            offer_id="offer-1", version=1, provider_ref="merchant-1",
            category=ServiceCategory.PSYCH_SUPPORT,
            price=(PriceComponent("课程", 600000), PriceComponent("住宿", 80000)),
            effective_at=T0,
        ))
        case.submit_claim(Claim(
            claim_id="claim-1", merchant_ref="merchant-1", offer_ref="offer-1",
            category=ServiceCategory.PSYCH_SUPPORT, statement="缓解焦虑",
            evidence_refs=("shot-1",), submitted_at=T0,
        ))
        case.confirm_listing("claim-1", "rev-platform")
        case.review_boundary("claim-1", "rev-pro", approve=True)
        case.record_consent(Consent("consent-1", "consumer-1", frozenset({"service", "recording"}), T0))
        case.add_evidence(EvidenceItem("hash-1", "consent-1", T0 + timedelta(hours=1)))
        case.file_complaint("TS-1001", ComplaintFingerprint("contract-1", 680000, "m-001"))
        case.assign_obligation(Obligation("ob-1", "order-1", "merchant-1", "退还课程费用"))
        case.subcontract("ob-1", "sub-1")
        case.fulfill_obligation("ob-1", "sub-1")
        case.record_payment("order-1", 680000)
        case.record_deposit("merchant-1", 1000000)
        case.freeze("order-1", 680000, "f-1")
        case.refund("order-1", "merchant-1", 680000, "r-1")
        case.deduct_deposit("merchant-1", 50000, "d-1")
        case.start_deadline(DeadlineKind.REFUND, timedelta(days=7))
        case.pause_deadline(DeadlineKind.REFUND)
        case.resume_deadline(DeadlineKind.REFUND)
        case.record_disposition("责令退款并下架违规宣传")

        self.assertNotEqual([], case.events)
        for event in case.events:
            self.assertEqual([], validate_event(event, SCHEMA), msg=event["event_id"])

    def test_versions_increment_per_aggregate(self) -> None:
        case = build_case()
        case.record_consent(Consent("consent-1", "consumer-1", frozenset({"service"}), T0))
        case.withdraw_consent("consent-1")
        case.assign_obligation(Obligation("ob-1", "order-1", "merchant-1", "退款"))
        case.fulfill_obligation("ob-1", "merchant-1")
        by_aggregate: dict[tuple[str, str], list[int]] = {}
        for event in case.events:
            key = (event["aggregate_type"], event["aggregate_id"])
            by_aggregate.setdefault(key, []).append(event["version"])
        for versions in by_aggregate.values():
            self.assertEqual(list(range(1, len(versions) + 1)), versions)

    def test_duplicate_complaint_emits_no_new_event(self) -> None:
        case = build_case()
        fingerprint = ComplaintFingerprint("contract-1", 680000, "m-001")
        case.file_complaint("TS-1001", fingerprint)
        count = len(case.events)
        repeated = case.file_complaint("TS-1001", fingerprint)
        self.assertEqual("R-000001", repeated.receipt_no)
        self.assertEqual(count, len(case.events))

    def test_split_complaint_links_to_original_receipt(self) -> None:
        case = build_case()
        case.file_complaint("TS-1001", ComplaintFingerprint("contract-1", 680000, "m-001"))
        split = case.file_complaint("TS-1001", ComplaintFingerprint("contract-1", 980000, "m-001"))
        self.assertEqual("R-000001", split.linked_to)
        split_events = [e for e in case.events if e["event_type"] == "COMPLAINT_SPLIT"]
        self.assertEqual(1, len(split_events))
        self.assertEqual("R-000001", split_events[0]["payload"]["linked_to"])

    def test_cross_region_parties_are_tracked(self) -> None:
        case = build_case()
        case.assign_obligation(Obligation("ob-1", "order-1", "merchant-1", "退款"))
        case.subcontract("ob-1", "sub-1")
        self.assertEqual(["云南", "浙江", "海南"], case.regions)
        self.assertEqual(["merchant-1", "sub-1"], case.parties)
        self.assertEqual("merchant-1", case.obligations.responsible_for("ob-1"))

    def test_disposition_freezes_rule_version_and_evidence(self) -> None:
        case = build_case()
        case.record_consent(Consent("consent-1", "consumer-1", frozenset({"service"}), T0))
        case.add_evidence(EvidenceItem("hash-1", "consent-1", T0 + timedelta(hours=1)))
        disposition = case.record_disposition("责令退款")
        case.update_rule_version("rules-2026v2")
        self.assertEqual("rules-2026v1", disposition.rule_version)
        self.assertEqual(("hash-1",), disposition.evidence_hashes)
        with self.assertRaises(ValueError):
            case.record_disposition("重复处理")

    def test_deadline_pause_resume_via_case(self) -> None:
        case = build_case()
        case.start_deadline(DeadlineKind.COOLING_OFF, timedelta(days=7))
        case.clock.advance(timedelta(days=2))
        case.pause_deadline(DeadlineKind.COOLING_OFF)
        case.clock.advance(timedelta(days=30))
        case.resume_deadline(DeadlineKind.COOLING_OFF)
        self.assertEqual(timedelta(days=5), case.deadlines.remaining(case.case_id, DeadlineKind.COOLING_OFF))
        self.assertEqual(DeadlineStatus.RUNNING, case.deadlines.status(case.case_id, DeadlineKind.COOLING_OFF))

    def test_merchant_self_approval_is_blocked_at_case_level(self) -> None:
        case = build_case()
        case.submit_claim(Claim(
            claim_id="claim-1", merchant_ref="merchant-1", offer_ref="offer-1",
            category=ServiceCategory.MEDICAL_TREATMENT, statement="疗愈抑郁症",
            evidence_refs=(), submitted_at=T0,
        ))
        case.confirm_listing("claim-1", "rev-platform")
        with self.assertRaises(PermissionError):
            case.review_boundary("claim-1", "rev-merchant", approve=True)
        claim = case.review_boundary("claim-1", "rev-pro", approve=False)
        self.assertEqual(ClaimStatus.REJECTED, claim.status)


if __name__ == "__main__":
    unittest.main()
