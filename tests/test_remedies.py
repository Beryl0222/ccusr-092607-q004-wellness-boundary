import threading
import unittest
from decimal import Decimal

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import make_casebook, make_complaint

from wellness_boundary import RemedyKind, RemedyOperation
from wellness_boundary.errors import (
    BalanceExceededError,
    DomainError,
    RemedyConflictError,
)


def make_op(case_id, key, kind=RemedyKind.REFUND, amount="600.00", obligor="mer-001"):
    return RemedyOperation(
        idempotency_key=key,
        case_id=case_id,
        kind=kind,
        obligor_ref=obligor,
        amount=Decimal(amount),
        currency="CNY",
        reason="测试",
    )


class RemedyLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.casebook, self.clock = make_casebook()
        self.case = self.casebook.open_case(make_complaint(), fingerprint="fp")
        self.ledger = self.casebook.remedies
        self.case_id = self.case.case_id

    def test_idempotent_replay_does_not_double_apply(self) -> None:
        record = self.casebook.execute_remedy(make_op(self.case_id, "k-1"))
        replay = self.casebook.execute_remedy(make_op(self.case_id, "k-1"))
        self.assertFalse(record.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(record.sequence, replay.sequence)
        self.assertEqual(Decimal("600.00"), self.ledger.total(self.case_id, RemedyKind.REFUND))
        events = [e for e in self.case.events.all() if e["event_type"] == "REMEDY_EXECUTED"]
        self.assertEqual(1, len(events))  # 重放不重复登记事件

    def test_same_key_with_different_content_is_rejected(self) -> None:
        self.casebook.execute_remedy(make_op(self.case_id, "k-1"))
        with self.assertRaises(RemedyConflictError):
            self.casebook.execute_remedy(make_op(self.case_id, "k-1", amount="601.00"))

    def test_refund_cannot_exceed_limit(self) -> None:
        self.ledger.set_limit(self.case_id, RemedyKind.REFUND, Decimal("1000.00"))
        self.casebook.execute_remedy(make_op(self.case_id, "k-1"))
        with self.assertRaises(BalanceExceededError):
            self.casebook.execute_remedy(make_op(self.case_id, "k-2", amount="500.00"))
        self.assertEqual(Decimal("600.00"), self.ledger.total(self.case_id, RemedyKind.REFUND))

    def test_deposit_deduction_has_independent_limit(self) -> None:
        self.ledger.set_limit(self.case_id, RemedyKind.DEPOSIT_DEDUCTION, Decimal("300.00"))
        self.casebook.execute_remedy(make_op(self.case_id, "d-1", RemedyKind.DEPOSIT_DEDUCTION, "300.00"))
        with self.assertRaises(BalanceExceededError):
            self.casebook.execute_remedy(make_op(self.case_id, "d-2", RemedyKind.DEPOSIT_DEDUCTION, "0.01"))
        # 冻结不受扣划额度影响
        self.casebook.execute_remedy(make_op(self.case_id, "f-1", RemedyKind.FREEZE, "5000.00"))

    def test_non_positive_amount_rejected(self) -> None:
        with self.assertRaises(DomainError):
            self.casebook.execute_remedy(make_op(self.case_id, "k-1", amount="0"))

    def test_concurrent_identical_operations_apply_once(self) -> None:
        barrier = threading.Barrier(8)
        results = []

        def worker():
            barrier.wait()
            results.append(self.casebook.execute_remedy(make_op(self.case_id, "k-1")))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(1, len({record.sequence for record in results}))
        self.assertEqual(1, sum(1 for record in results if not record.replayed))
        self.assertEqual(Decimal("600.00"), self.ledger.total(self.case_id, RemedyKind.REFUND))
        self.assertEqual(1, len(self.ledger.records_for_case(self.case_id)))

    def test_concurrent_distinct_operations_respect_limit(self) -> None:
        self.ledger.set_limit(self.case_id, RemedyKind.REFUND, Decimal("1000.00"))
        barrier = threading.Barrier(6)
        outcomes = []

        def worker(index):
            barrier.wait()
            try:
                outcomes.append(self.casebook.execute_remedy(make_op(self.case_id, f"k-{index}", amount="400.00")))
            except BalanceExceededError:
                outcomes.append("rejected")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        applied = [o for o in outcomes if o != "rejected"]
        self.assertEqual(2, len(applied))  # 1000 额度内最多两笔 400
        self.assertEqual(Decimal("800.00"), self.ledger.total(self.case_id, RemedyKind.REFUND))


if __name__ == "__main__":
    unittest.main()
