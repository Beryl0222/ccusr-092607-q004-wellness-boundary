import unittest
from datetime import timedelta

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import T0, make_casebook, make_claim, make_complaint, make_provider

from wellness_boundary import (
    ClaimClass,
    Qualification,
    QualificationKind,
    Reviewer,
    ReviewerRole,
    ReviewOutcome,
    ReviewScope,
    claim_exceeds_license,
    qualification_ceiling,
    submit_review,
)
from wellness_boundary.errors import ReviewPermissionError, SelfApprovalError


class QualificationCeilingTests(unittest.TestCase):
    def test_ceiling_follows_highest_valid_qualification(self) -> None:
        wellness_only = make_provider(kinds=("wellness_operation",))
        self.assertEqual(ClaimClass.GENERAL_EXPERIENCE, qualification_ceiling(wellness_only))
        with_psych = make_provider(kinds=("wellness_operation", "psychological_support_permit"))
        self.assertEqual(ClaimClass.PSYCHOLOGICAL_SUPPORT, qualification_ceiling(with_psych))
        with_medical = make_provider(kinds=("medical_institution_license",))
        self.assertEqual(ClaimClass.MEDICAL_TREATMENT, qualification_ceiling(with_medical))

    def test_expired_qualification_does_not_raise_ceiling(self) -> None:
        provider = make_provider(kinds=("medical_institution_license",))
        provider.qualifications.append(
            Qualification(
                kind=QualificationKind.MEDICAL_INSTITUTION_LICENSE,
                certificate_no="CERT-expired",
                issuer="省监管局",
                valid_from=T0 - timedelta(days=800),
                valid_until=T0 - timedelta(days=400),
            )
        )
        # 过期资质不计入：仍按有效的医疗资质（400 天前起）判定
        self.assertEqual(ClaimClass.MEDICAL_TREATMENT, qualification_ceiling(provider, T0))
        provider.qualifications.pop(0)
        self.assertEqual(ClaimClass.GENERAL_EXPERIENCE, qualification_ceiling(provider, T0))

    def test_claim_exceeds_license(self) -> None:
        provider = make_provider(kinds=("wellness_operation",))
        medical_claim = make_claim(claim_class=ClaimClass.MEDICAL_TREATMENT)
        general_claim = make_claim(claim_class=ClaimClass.GENERAL_EXPERIENCE)
        self.assertTrue(claim_exceeds_license(provider, medical_claim))
        self.assertFalse(claim_exceeds_license(provider, general_claim))


class ReviewSeparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.casebook, self.clock = make_casebook()
        self.case = self.casebook.open_case(
            make_complaint(), fingerprint="fp", parties=[make_provider()]
        )
        self.case.register_claim(make_claim())
        self.platform = Reviewer("rev-plat", ReviewerRole.PLATFORM)
        self.professional = Reviewer("rev-prof", ReviewerRole.PROFESSIONAL)
        self.merchant = Reviewer("mer-001", ReviewerRole.MERCHANT, merchant_ref="mer-001")

    def review(self, reviewer, scope, outcome=ReviewOutcome.APPROVED):
        return submit_review(
            self.case,
            "claim-1",
            reviewer=reviewer,
            scope=scope,
            outcome=outcome,
            rule_version="RB-2026-09",
            rationale="测试",
            now=self.clock.now(),
        )

    def test_platform_confirms_listing_only(self) -> None:
        decision = self.review(self.platform, ReviewScope.LISTING)
        self.assertEqual(ReviewScope.LISTING, decision.scope)
        with self.assertRaises(ReviewPermissionError):
            self.review(self.platform, ReviewScope.RISK_BOUNDARY)

    def test_professional_owns_risk_boundary_only(self) -> None:
        decision = self.review(self.professional, ReviewScope.RISK_BOUNDARY, ReviewOutcome.FLAGGED)
        self.assertEqual(ReviewOutcome.FLAGGED, decision.outcome)
        with self.assertRaises(ReviewPermissionError):
            self.review(self.professional, ReviewScope.LISTING)

    def test_merchant_cannot_approve_own_claim(self) -> None:
        # 自我批准触发专门的自我批准禁令，先于审查范围校验
        with self.assertRaises(SelfApprovalError):
            self.review(self.merchant, ReviewScope.LISTING)

    def test_merchant_cannot_screen_at_all(self) -> None:
        # 商家不是任何审查范围的合格审查人
        with self.assertRaises(ReviewPermissionError):
            self.review(self.merchant, ReviewScope.LISTING, ReviewOutcome.FLAGGED)
        with self.assertRaises(ReviewPermissionError):
            self.review(self.merchant, ReviewScope.RISK_BOUNDARY, ReviewOutcome.FLAGGED)

    def test_review_is_recorded_as_contract_event(self) -> None:
        self.review(self.professional, ReviewScope.RISK_BOUNDARY, ReviewOutcome.FLAGGED)
        events = [e for e in self.case.events.all() if e["event_type"] == "CLAIM_SCREENED"]
        self.assertEqual(1, len(events))
        self.assertEqual("RB-2026-09", events[0]["payload"]["rule_version"])
        self.assertEqual("risk_boundary", events[0]["payload"]["review_scope"])


if __name__ == "__main__":
    unittest.main()
