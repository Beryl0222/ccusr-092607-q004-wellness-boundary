import unittest
from datetime import timedelta
from decimal import Decimal

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import (
    T0,
    make_casebook,
    make_chain,
    make_claim,
    make_complaint,
    make_parties,
)

from wellness_boundary import (
    ComplaintService,
    DeadlineKind,
    Disposition,
    DisputeMaterial,
    Obligation,
    ObligationKind,
    RemedyKind,
    RemedyOperation,
    Reviewer,
    ReviewerRole,
    ReviewOutcome,
    ReviewScope,
    RuleBook,
    RuleSet,
    consumer_view,
    regulator_view,
    submit_review,
    trace_disposition,
)
from wellness_boundary.errors import AccessDeniedError, DispositionStateError


class ViewScenario:
    """搭好一单跨地区案卷：越界宣传、审查、义务、期限、退款与最终处理。"""

    def __init__(self) -> None:
        self.casebook, self.clock = make_casebook()
        self.service = ComplaintService(self.casebook, self.clock)
        self.receipt = self.service.file(
            make_complaint(), chain=make_chain(), parties=make_parties()
        )
        self.case = self.casebook.get(self.receipt.case_id)
        self.case.register_claim(make_claim())  # 无医疗资质主体的医疗功效宣传
        self.case.register_material(
            DisputeMaterial("mat-1", "consumer-1", "screenshot", "sha-ad-1", "dispute", "consumer-1", T0)
        )
        submit_review(
            self.case, "claim-1",
            reviewer=Reviewer("rev-plat", ReviewerRole.PLATFORM),
            scope=ReviewScope.LISTING, outcome=ReviewOutcome.APPROVED,
            rule_version="RB-2026-09", rationale="上架信息一致", now=self.clock.now(),
        )
        submit_review(
            self.case, "claim-1",
            reviewer=Reviewer("rev-prof", ReviewerRole.PROFESSIONAL),
            scope=ReviewScope.RISK_BOUNDARY, outcome=ReviewOutcome.FLAGGED,
            rule_version="RB-2026-09", rationale="越过医疗诊疗边界", now=self.clock.now(),
        )
        deadline = self.casebook.open_deadline(self.case.case_id, DeadlineKind.REFUND, timedelta(days=15))
        self.case.assign_obligation(
            Obligation("ob-refund", self.case.case_id, ObligationKind.REFUND, "mer-001",
                       "退还全部费用", T0, deadline_id=deadline.deadline_id)
        )
        self.case.delegate_obligation("ob-refund", "sub-001", self.clock.now())
        self.casebook.remedies.set_limit(self.case.case_id, RemedyKind.REFUND, Decimal("1280.00"))
        self.casebook.execute_remedy(
            RemedyOperation("k-1", self.case.case_id, RemedyKind.REFUND, "mer-001",
                            Decimal("1280.00"), "CNY", "冷静期内全额退款")
        )
        self.rulebook = RuleBook()
        self.rulebook.register(RuleSet("RB-2026-09", T0 - timedelta(days=30), None, "现行边界规则", ("医疗功效宣传须持医疗资质",)))
        self.case.dispose(
            Disposition("disp-1", self.clock.now(), "RB-2026-09", "认定越界宣传，责令退款并整改", "监管员甲"),
            self.rulebook,
        )


class RegulatorViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = ViewScenario()
        self.view = regulator_view(self.scenario.casebook, self.scenario.case.case_id)

    def test_every_claim_shows_license_boundary(self) -> None:
        (claim,) = self.view["claims"]
        self.assertTrue(claim["exceeds_license"])  # 每条宣传是否超出许可
        self.assertEqual("general_experience", claim["permitted_ceiling"])
        self.assertEqual("medical_treatment", claim["claim_class"])
        self.assertEqual("flagged", claim["boundary_review"])
        self.assertTrue(claim["listing_confirmed"])

    def test_outstanding_obligations_grouped_by_party(self) -> None:
        by_party = self.view["obligations_by_party"]
        self.assertIn("mer-001", by_party)  # 责任仍在原责任方
        (obligation,) = by_party["mer-001"]
        self.assertEqual("sub-001", obligation["delegated_to"])  # 转包只记执行方
        self.assertEqual("refund", obligation["kind"])
        self.assertEqual(15 * 86400, obligation["deadline"]["remaining_seconds"])

    def test_responsibility_chain_spans_regions(self) -> None:
        chain = self.view["responsibility_chain"]
        self.assertEqual(["seller", "platform", "subcontractor"], [link["role"] for link in chain])
        self.assertEqual({"浙江杭州", "上海", "四川成都"}, {link["region"] for link in chain})
        seller = next(link for link in chain if link["role"] == "seller")
        self.assertEqual(1, seller["outstanding_count"])

    def test_remedy_and_deadline_visible(self) -> None:
        self.assertEqual("1280.00", self.view["remedies"][0]["amount"])
        self.assertEqual(1, len(self.view["deadlines"]))


class ConsumerViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = ViewScenario()
        self.view = consumer_view(self.scenario.casebook, self.scenario.case.case_id, "consumer-1")

    def test_minimal_case_info_with_clear_responsible_party(self) -> None:
        self.assertEqual(self.scenario.receipt.receipt_no, self.view["receipt_no"])
        self.assertEqual("mer-001", self.view["responsible_party"]["party_ref"])
        self.assertEqual("云栖疗愈工作室", self.view["responsible_party"]["name"])
        self.assertEqual("1280.00", self.view["refunds"][0]["amount"])
        self.assertEqual("认定越界宣传，责令退款并整改", self.view["disposition"]["summary"])

    def test_internal_review_details_not_exposed(self) -> None:
        self.assertNotIn("claims", self.view)
        self.assertNotIn("evidence", self.view)
        self.assertNotIn("obligations_by_party", self.view)

    def test_other_consumer_denied(self) -> None:
        with self.assertRaises(AccessDeniedError):
            consumer_view(self.scenario.casebook, self.scenario.case.case_id, "consumer-2")


class TraceDispositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = ViewScenario()
        self.trace = trace_disposition(
            self.scenario.casebook, self.scenario.case.case_id, self.scenario.rulebook
        )

    def test_traces_to_rule_effective_at_decision_time(self) -> None:
        rule_set = self.trace["rule_set"]
        self.assertEqual("RB-2026-09", rule_set["rule_version"])
        self.assertTrue(rule_set["was_effective_at_decision"])
        self.assertEqual(("医疗功效宣传须持医疗资质",), tuple(rule_set["provisions"]))

    def test_traces_complete_evidence_and_event_chain(self) -> None:
        hashes = {item["sha256"] for item in self.trace["evidence_chain"]}
        self.assertIn("sha-ad-1", hashes)
        event_types = [event["event_type"] for event in self.trace["events"]]
        self.assertEqual(
            ["CASE_OPENED", "CLAIM_SCREENED", "CLAIM_SCREENED", "REMEDY_EXECUTED"],
            event_types,
        )
        versions = [event["version"] for event in self.trace["events"]]
        self.assertEqual(sorted(versions), versions)

    def test_trace_before_disposition_rejected(self) -> None:
        casebook, _ = make_casebook()
        case = casebook.open_case(make_complaint(), fingerprint="fp")
        with self.assertRaises(DispositionStateError):
            trace_disposition(casebook, case.case_id, RuleBook())


if __name__ == "__main__":
    unittest.main()
