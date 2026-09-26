import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from support import T0
from wellness_boundary.complaints import ComplaintDesk, ComplaintFingerprint

FP_A = ComplaintFingerprint(contract_ref="contract-1", amount_cents=680000, material_hash="m-001")


class ComplaintDeskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.desk = ComplaintDesk()

    def test_new_complaint_gets_receipt(self) -> None:
        case, outcome = self.desk.file("TS-1001", FP_A, T0)
        self.assertEqual("new", outcome)
        self.assertEqual("R-000001", case.receipt_no)
        self.assertIsNone(case.linked_to)

    def test_duplicate_complaint_reuses_original_receipt(self) -> None:
        first, _ = self.desk.file("TS-1001", FP_A, T0)
        again, outcome = self.desk.file("TS-1001", FP_A, T0)
        self.assertEqual("duplicate", outcome)
        self.assertEqual(first.receipt_no, again.receipt_no)
        self.assertEqual(1, again.duplicates)
        self.assertEqual(1, len(self.desk.cases_for("TS-1001")))

    def test_same_number_different_fingerprint_is_investigated_separately(self) -> None:
        first, _ = self.desk.file("TS-1001", FP_A, T0)
        variants = [
            ComplaintFingerprint("contract-2", FP_A.amount_cents, FP_A.material_hash),  # 合同不同
            ComplaintFingerprint(FP_A.contract_ref, 980000, FP_A.material_hash),        # 金额不同
            ComplaintFingerprint(FP_A.contract_ref, FP_A.amount_cents, "m-002"),        # 材料指纹不同
        ]
        for index, fingerprint in enumerate(variants):
            case, outcome = self.desk.file("TS-1001", fingerprint, T0)
            self.assertEqual("split", outcome)
            self.assertEqual(f"R-{index + 2:06d}", case.receipt_no)
            self.assertEqual(first.receipt_no, case.linked_to)
        self.assertEqual(4, len(self.desk.cases_for("TS-1001")))

    def test_empty_complaint_number_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.desk.file("  ", FP_A, T0)


if __name__ == "__main__":
    unittest.main()
