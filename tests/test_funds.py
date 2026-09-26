import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from support import T0
from wellness_boundary.funds import FundsLedger, FundsOpKind


class FundsLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = FundsLedger()
        self.ledger.record_payment("order-1", 680000)
        self.ledger.record_deposit("merchant-1", 1000000)

    def test_idempotent_replay_returns_original_without_double_effect(self) -> None:
        first = self.ledger.refund("order-1", 680000, "refund-key-1", T0)
        replay = self.ledger.refund("order-1", 680000, "refund-key-1", T0)
        self.assertIs(first, replay)
        self.assertEqual(680000, self.ledger.refunded_of("order-1"))  # 只执行一次

    def test_same_key_with_different_payload_is_a_conflict(self) -> None:
        self.ledger.freeze("order-1", 100000, "key-1", T0)
        with self.assertRaises(ValueError):
            self.ledger.freeze("order-1", 200000, "key-1", T0)
        with self.assertRaises(ValueError):
            self.ledger.refund("order-1", 100000, "key-1", T0)

    def test_concurrent_duplicate_keys_cannot_overdraw(self) -> None:
        self.ledger.refund("order-1", 400000, "k-1", T0)
        self.ledger.refund("order-1", 200000, "k-2", T0)
        with self.assertRaises(ValueError):
            self.ledger.refund("order-1", 100000, "k-3", T0)  # 累计超过实收
        self.assertEqual(600000, self.ledger.refunded_of("order-1"))

    def test_freeze_cannot_exceed_payment(self) -> None:
        self.ledger.freeze("order-1", 680000, "f-1", T0)
        with self.assertRaises(ValueError):
            self.ledger.freeze("order-1", 1, "f-2", T0)
        with self.assertRaises(ValueError):
            self.ledger.freeze("order-unknown", 1, "f-3", T0)

    def test_deposit_deduction_capped_and_idempotent(self) -> None:
        op = self.ledger.deduct_deposit("merchant-1", 300000, "d-1", T0)
        self.assertEqual(FundsOpKind.DEPOSIT_DEDUCT, op.kind)
        self.assertIs(op, self.ledger.deduct_deposit("merchant-1", 300000, "d-1", T0))
        self.ledger.deduct_deposit("merchant-1", 700000, "d-2", T0)
        with self.assertRaises(ValueError):
            self.ledger.deduct_deposit("merchant-1", 1, "d-3", T0)
        self.assertEqual(1000000, self.ledger.deducted_of("merchant-1"))

    def test_key_and_amount_are_validated(self) -> None:
        with self.assertRaises(ValueError):
            self.ledger.refund("order-1", 100, " ", T0)
        with self.assertRaises(ValueError):
            self.ledger.refund("order-1", 0, "k-9", T0)


if __name__ == "__main__":
    unittest.main()
