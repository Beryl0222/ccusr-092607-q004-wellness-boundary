import unittest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import T0, make_validator

from wellness_boundary import EventLog
from wellness_boundary.errors import ContractViolationError, EventConflictError


class EventLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.log = EventLog(make_validator())

    def test_versions_increase_per_aggregate(self) -> None:
        first = self.log.record("CASE_OPENED", "consumer_case", "CASE-1", T0, {
            "contract_snapshot": "h1", "evidence_hashes": [],
        })
        second = self.log.record("REMEDY_EXECUTED", "consumer_case", "CASE-1", T0, {
            "obligor_ref": "mer-001", "amount": "10.00",
        })
        other = self.log.record("OFFER_VERSIONED", "wellness_offer", "offer-1@1", T0, {})
        self.assertEqual(1, first["version"])
        self.assertEqual(2, second["version"])
        self.assertEqual(1, other["version"])  # 不同聚合各自编号

    def test_same_event_id_and_content_is_idempotent(self) -> None:
        payload = {"contract_snapshot": "h1", "evidence_hashes": ["a"]}
        first = self.log.record("CASE_OPENED", "consumer_case", "CASE-1", T0, payload, event_id="evt-1")
        replay = self.log.record("CASE_OPENED", "consumer_case", "CASE-1", T0, payload, event_id="evt-1")
        self.assertIs(first, replay)
        self.assertEqual(1, len(self.log))

    def test_same_event_id_with_different_content_is_rejected(self) -> None:
        self.log.record("CASE_OPENED", "consumer_case", "CASE-1", T0, {
            "contract_snapshot": "h1", "evidence_hashes": [],
        }, event_id="evt-1")
        with self.assertRaises(EventConflictError):
            self.log.record("CASE_OPENED", "consumer_case", "CASE-1", T0, {
                "contract_snapshot": "tampered", "evidence_hashes": [],
            }, event_id="evt-1")
        self.assertEqual(1, len(self.log))

    def test_contract_violation_blocks_record(self) -> None:
        with self.assertRaises(ContractViolationError):
            # CLAIM_SCREENED 缺少契约要求的 rule_version / review_scope
            self.log.record("CLAIM_SCREENED", "marketing_claim", "claim-1", T0, {})
        self.assertEqual(0, len(self.log))

    def test_without_validator_still_assigns_versions(self) -> None:
        log = EventLog()
        event = log.record("OFFER_VERSIONED", "wellness_offer", "offer-9@1", T0, {})
        self.assertEqual(1, event["version"])


if __name__ == "__main__":
    unittest.main()
