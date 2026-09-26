import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wellness_boundary.contracts import validate_event


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads((ROOT / "contracts/domain.schema.json").read_text(encoding="utf-8"))
        cls.sample = json.loads((ROOT / "data/sample.json").read_text(encoding="utf-8"))

    def test_sample_is_valid(self) -> None:
        self.assertEqual([], validate_event(self.sample, self.schema))

    def test_missing_fields_are_stable(self) -> None:
        issues = validate_event({}, self.schema)
        self.assertEqual(sorted(x.field for x in issues), [x.field for x in issues])

    def test_time_and_version_boundaries(self) -> None:
        event = dict(self.sample, occurred_at="2026-09-25T10:00:00", version=0)
        codes = {(x.field, x.code) for x in validate_event(event, self.schema)}
        self.assertIn(("occurred_at", "timezone_required"), codes)
        self.assertIn(("version", "positive_integer"), codes)

    def test_event_payload_is_required(self) -> None:
        event = dict(self.sample, event_type="CLAIM_SCREENED", payload={})
        self.assertIn(("payload.rule_version", "required"), [(x.field, x.code) for x in validate_event(event, self.schema)])

    def test_unknown_event_is_rejected(self) -> None:
        issues = validate_event(dict(self.sample, event_type="UNKNOWN"), self.schema)
        self.assertIn(("event_type", "unsupported_value"), [(x.field, x.code) for x in issues])

    def test_disposition_sample_is_valid(self) -> None:
        sample = json.loads((ROOT / "data/sample_disposition.json").read_text(encoding="utf-8"))
        self.assertEqual([], validate_event(sample, self.schema))

    def test_new_event_payloads_are_enforced(self) -> None:
        event = dict(self.sample, event_type="REFUND_ISSUED", aggregate_type="payment", payload={"order_ref": "o-1"})
        fields = {x.field for x in validate_event(event, self.schema)}
        self.assertIn("payload.amount_cents", fields)
        self.assertIn("payload.idempotency_key", fields)
        split = dict(self.sample, event_type="COMPLAINT_SPLIT", aggregate_type="complaint", payload={"complaint_no": "TS-1"})
        fields = {x.field for x in validate_event(split, self.schema)}
        self.assertIn("payload.receipt_no", fields)
        self.assertIn("payload.linked_to", fields)


if __name__ == "__main__":
    unittest.main()
