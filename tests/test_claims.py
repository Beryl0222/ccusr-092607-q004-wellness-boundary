import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from support import T0, build_registry
from wellness_boundary.claims import Claim, ClaimDesk, ClaimStatus
from wellness_boundary.registry import ServiceCategory


def make_claim(claim_id: str, merchant: str, category: ServiceCategory) -> Claim:
    return Claim(
        claim_id=claim_id,
        merchant_ref=merchant,
        offer_ref="offer-1",
        category=category,
        statement="七天禅修营显著改善焦虑",
        evidence_refs=("shot-1",),
        submitted_at=T0,
    )


class ClaimReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_registry()
        self.desk = ClaimDesk(self.registry)

    def test_platform_only_confirms_listing(self) -> None:
        self.desk.submit(make_claim("c-1", "merchant-1", ServiceCategory.PSYCH_SUPPORT))
        claim = self.desk.confirm_listing("c-1", "rev-platform", T0)
        self.assertEqual(ClaimStatus.LISTING_CONFIRMED, claim.status)
        with self.assertRaises(PermissionError):
            self.desk.review_boundary("c-1", "rev-platform", True, "rules-2026v1", T0)

    def test_non_platform_cannot_confirm_listing(self) -> None:
        self.desk.submit(make_claim("c-2", "merchant-1", ServiceCategory.PSYCH_SUPPORT))
        with self.assertRaises(PermissionError):
            self.desk.confirm_listing("c-2", "rev-pro", T0)

    def test_merchant_cannot_approve_own_claims(self) -> None:
        self.desk.submit(make_claim("c-3", "merchant-1", ServiceCategory.PSYCH_SUPPORT))
        self.desk.confirm_listing("c-3", "rev-platform", T0)
        with self.assertRaises(PermissionError):
            self.desk.review_boundary("c-3", "rev-merchant", True, "rules-2026v1", T0)

    def test_affiliated_professional_counts_as_self_approval(self) -> None:
        self.desk.submit(make_claim("c-4", "merchant-1", ServiceCategory.PSYCH_SUPPORT))
        self.desk.confirm_listing("c-4", "rev-platform", T0)
        with self.assertRaises(PermissionError):
            self.desk.review_boundary("c-4", "rev-pro-captured", True, "rules-2026v1", T0)

    def test_independent_professional_decides_boundary(self) -> None:
        self.desk.submit(make_claim("c-5", "merchant-1", ServiceCategory.PSYCH_SUPPORT))
        self.desk.confirm_listing("c-5", "rev-platform", T0)
        claim = self.desk.review_boundary("c-5", "rev-pro", False, "rules-2026v1", T0)
        self.assertEqual(ClaimStatus.REJECTED, claim.status)
        self.assertEqual("rules-2026v1", claim.rule_version)
        self.assertEqual("rev-pro", claim.reviewer_ref)

    def test_boundary_review_requires_listing_first(self) -> None:
        self.desk.submit(make_claim("c-6", "merchant-1", ServiceCategory.PSYCH_SUPPORT))
        with self.assertRaises(ValueError):
            self.desk.review_boundary("c-6", "rev-pro", True, "rules-2026v1", T0)

    def test_exceeds_license_by_category(self) -> None:
        self.desk.submit(make_claim("c-7", "merchant-1", ServiceCategory.MEDICAL_TREATMENT))
        self.desk.submit(make_claim("c-8", "merchant-1", ServiceCategory.PSYCH_SUPPORT))
        self.desk.submit(make_claim("c-9", "merchant-2", ServiceCategory.PSYCH_SUPPORT))
        self.desk.submit(make_claim("c-10", "merchant-2", ServiceCategory.GENERAL_EXPERIENCE))
        self.assertTrue(self.desk.exceeds_license("c-7", T0))    # 无医疗执业资质
        self.assertFalse(self.desk.exceeds_license("c-8", T0))   # 持有心理支持资质
        self.assertTrue(self.desk.exceeds_license("c-9", T0))    # 无任何资质
        self.assertFalse(self.desk.exceeds_license("c-10", T0))  # 普通体验无门槛


if __name__ == "__main__":
    unittest.main()
