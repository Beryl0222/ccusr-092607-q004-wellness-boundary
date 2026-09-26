import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from wellness_boundary.responsibility import Obligation, ObligationStatus, ResponsibilityChain


class ResponsibilityChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.chain = ResponsibilityChain()
        self.chain.assign(Obligation("ob-1", "order-1", "merchant-1", "退还课程费用"))
        self.chain.assign(Obligation("ob-2", "order-1", "merchant-1", "提供服务记录"))
        self.chain.assign(Obligation("ob-3", "order-1", "merchant-2", "下架违规宣传"))

    def test_subcontracting_does_not_move_responsibility(self) -> None:
        self.chain.subcontract("ob-1", "sub-1")
        self.assertEqual("merchant-1", self.chain.responsible_for("ob-1"))
        self.assertEqual("sub-1", self.chain.get("ob-1").performer_ref)

    def test_performer_can_fulfill_but_strangers_cannot(self) -> None:
        self.chain.subcontract("ob-1", "sub-1")
        fulfilled = self.chain.fulfill("ob-1", "sub-1")
        self.assertEqual(ObligationStatus.FULFILLED, fulfilled.status)
        self.assertEqual("merchant-1", self.chain.responsible_for("ob-1"))
        with self.assertRaises(PermissionError):
            self.chain.fulfill("ob-2", "sub-1")

    def test_fulfill_and_subcontract_are_one_way(self) -> None:
        self.chain.fulfill("ob-1", "merchant-1")
        with self.assertRaises(ValueError):
            self.chain.fulfill("ob-1", "merchant-1")
        with self.assertRaises(ValueError):
            self.chain.subcontract("ob-1", "sub-1")
        with self.assertRaises(ValueError):
            self.chain.subcontract("ob-2", "merchant-1")  # 自身履约不构成转包

    def test_unfulfilled_is_grouped_by_obligor(self) -> None:
        self.chain.fulfill("ob-3", "merchant-2")
        self.assertEqual(["ob-1", "ob-2"], [o.obligation_id for o in self.chain.unfulfilled("merchant-1")])
        self.assertEqual([], self.chain.unfulfilled("merchant-2"))
        self.assertEqual(2, len(self.chain.unfulfilled()))


if __name__ == "__main__":
    unittest.main()
