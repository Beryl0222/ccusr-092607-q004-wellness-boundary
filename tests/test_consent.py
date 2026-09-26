import sys
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from support import T0
from wellness_boundary.consent import (
    Consent,
    ConsentLedger,
    EvidenceItem,
    EvidenceVault,
    Purpose,
)


class ConsentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = ConsentLedger()
        self.consent = self.ledger.record(Consent(
            consent_id="consent-1",
            consumer_ref="consumer-1",
            scopes=frozenset({"service", "recording"}),
            granted_at=T0,
        ))
        self.vault = EvidenceVault(self.ledger)
        self.vault.deposit(EvidenceItem("hash-1", "consent-1", T0 + timedelta(days=1)))

    def test_scope_allowed_before_withdrawal(self) -> None:
        self.assertTrue(self.ledger.permits("consent-1", "service", T0 + timedelta(days=2)))
        self.assertFalse(self.ledger.permits("consent-1", "marketing", T0 + timedelta(days=2)))

    def test_withdrawal_stops_future_services_and_new_uses(self) -> None:
        withdrawn_at = T0 + timedelta(days=3)
        self.ledger.withdraw("consent-1", withdrawn_at)
        self.assertFalse(self.ledger.permits("consent-1", "service", withdrawn_at))
        self.assertFalse(self.ledger.permits("consent-1", "recording", withdrawn_at + timedelta(days=1)))
        # 撤回前已经发生的授权仍然有效
        self.assertTrue(self.ledger.permits("consent-1", "service", T0 + timedelta(days=1)))

    def test_withdrawal_is_final_and_not_retroactive(self) -> None:
        self.ledger.withdraw("consent-1", T0 + timedelta(days=3))
        with self.assertRaises(ValueError):
            self.ledger.withdraw("consent-1", T0 + timedelta(days=4))
        with self.assertRaises(ValueError):
            self.ledger.record(Consent("consent-1", "consumer-1", frozenset({"service"}), T0))

    def test_evidence_retained_but_restricted_after_withdrawal(self) -> None:
        self.ledger.withdraw("consent-1", T0 + timedelta(days=3))
        at = T0 + timedelta(days=4)
        # 依法保留：履约、争议与监管目的仍可访问
        for purpose in (Purpose.FULFILLMENT, Purpose.DISPUTE, Purpose.REGULATORY):
            self.assertEqual("hash-1", self.vault.access("hash-1", purpose, at).evidence_hash)
        # 限制访问：未来服务与新用途被拒绝
        for purpose in (Purpose.NEW_SERVICE, Purpose.MARKETING):
            with self.assertRaises(PermissionError):
                self.vault.access("hash-1", purpose, at)
        self.assertIn("hash-1", self.vault.hashes())

    def test_evidence_before_withdrawal_is_unrestricted(self) -> None:
        at = T0 + timedelta(days=2)
        self.assertEqual("hash-1", self.vault.access("hash-1", Purpose.MARKETING, at).evidence_hash)

    def test_evidence_must_predate_collection_consent(self) -> None:
        with self.assertRaises(ValueError):
            self.vault.deposit(EvidenceItem("hash-0", "consent-1", T0 - timedelta(days=1)))
        with self.assertRaises(KeyError):
            self.vault.deposit(EvidenceItem("hash-x", "consent-x", T0))


if __name__ == "__main__":
    unittest.main()
