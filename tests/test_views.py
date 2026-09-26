import sys
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from support import T0, build_registry
from wellness_boundary.casefile import CaseFile
from wellness_boundary.claims import Claim
from wellness_boundary.clock import ManualClock
from wellness_boundary.consent import Consent, EvidenceItem
from wellness_boundary.registry import ServiceCategory
from wellness_boundary.responsibility import Obligation
from wellness_boundary.views import consumer_view, regulator_view, trace_disposition


def build_case() -> CaseFile:
    case = CaseFile("case-0002", build_registry(), ManualClock(T0), rule_version="rules-2026v1")
    case.open("merchant-1", {"contract_ref": "contract-1"})
    case.submit_claim(Claim(
        claim_id="claim-medical", merchant_ref="merchant-2", offer_ref="offer-9",
        category=ServiceCategory.MEDICAL_TREATMENT, statement="在线疗愈替代药物治疗",
        evidence_refs=("shot-9",), submitted_at=T0,
    ))
    case.submit_claim(Claim(
        claim_id="claim-general", merchant_ref="merchant-1", offer_ref="offer-1",
        category=ServiceCategory.GENERAL_EXPERIENCE, statement="山林静修体验",
        evidence_refs=("shot-1",), submitted_at=T0,
    ))
    case.confirm_listing("claim-medical", "rev-platform")
    case.review_boundary("claim-medical", "rev-pro", approve=False)
    case.assign_obligation(Obligation("ob-1", "order-1", "merchant-1", "退还课程费用"))
    case.assign_obligation(Obligation("ob-2", "order-1", "merchant-2", "下架违规宣传"))
    case.record_consent(Consent("consent-1", "consumer-1", frozenset({"service"}), T0))
    case.add_evidence(EvidenceItem("hash-1", "consent-1", T0 + timedelta(hours=1)))
    return case


class RegulatorViewTests(unittest.TestCase):
    def test_claims_show_license_boundary_and_rules(self) -> None:
        view = regulator_view(build_case())
        claims = {c["claim_id"]: c for c in view["claims"]}
        self.assertTrue(claims["claim-medical"]["exceeds_license"])
        self.assertEqual("rejected", claims["claim-medical"]["status"])
        self.assertEqual("rules-2026v1", claims["claim-medical"]["rule_version"])
        self.assertFalse(claims["claim-general"]["exceeds_license"])
        self.assertEqual("submitted", claims["claim-general"]["status"])

    def test_unfulfilled_obligations_are_listed_per_party(self) -> None:
        case = build_case()
        case.fulfill_obligation("ob-1", "merchant-1")
        view = regulator_view(case)
        self.assertEqual({}, view["unfulfilled_obligations"].get("merchant-1", {}))
        self.assertEqual(["ob-2"], view["unfulfilled_obligations"]["merchant-2"])


class ConsumerViewTests(unittest.TestCase):
    def test_view_is_minimal_and_names_responsible_party(self) -> None:
        case = build_case()
        view = consumer_view(case)
        self.assertEqual({"case_id", "status", "responsible_party"}, set(view))
        self.assertEqual("open", view["status"])
        self.assertEqual(
            {"entity_id": "merchant-1", "name": "静修文旅"},
            view["responsible_party"],
        )
        case.record_disposition("责令退款")
        closed = consumer_view(case)
        self.assertEqual("closed", closed["status"])
        self.assertEqual("责令退款", closed["outcome"])


class TraceTests(unittest.TestCase):
    def test_trace_reaches_rules_and_evidence_effective_at_decision(self) -> None:
        case = build_case()
        case.record_disposition("责令退款并整改")
        case.update_rule_version("rules-2026v2")  # 规则事后演进不影响追溯
        trace = trace_disposition(case)
        self.assertEqual("rules-2026v1", trace["rule_version"])
        self.assertEqual(["hash-1"], [item["evidence_hash"] for item in trace["evidence_chain"]])
        self.assertEqual("consent-1", trace["evidence_chain"][0]["consent_ref"])
        self.assertNotEqual([], trace["event_trail"])

    def test_trace_requires_disposition(self) -> None:
        with self.assertRaises(ValueError):
            trace_disposition(build_case())


if __name__ == "__main__":
    unittest.main()
