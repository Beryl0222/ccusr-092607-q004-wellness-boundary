import threading
import unittest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import make_casebook, make_chain, make_complaint, make_parties

from wellness_boundary import ComplaintService


class ComplaintFilingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.casebook, self.clock = make_casebook()
        self.service = ComplaintService(self.casebook, self.clock)

    def file(self, complaint):
        return self.service.file(complaint, chain=make_chain(), parties=make_parties())

    def test_first_filing_opens_case_with_receipt(self) -> None:
        receipt = self.file(make_complaint())
        self.assertFalse(receipt.reused)
        case = self.casebook.get(receipt.case_id)
        self.assertEqual(receipt.receipt_no, case.receipt_no)
        self.assertEqual(3, len(case.chain))  # 跨地区责任链随案登记

    def test_duplicate_filing_reuses_original_receipt(self) -> None:
        first = self.file(make_complaint())
        again = self.file(make_complaint())
        self.assertTrue(again.reused)
        self.assertEqual(first.receipt_no, again.receipt_no)
        self.assertEqual(first.case_id, again.case_id)
        self.assertEqual(first.issued_at, again.issued_at)
        case = self.casebook.get(first.case_id)
        self.assertEqual(1, case.duplicate_filings)
        self.assertEqual(1, len(self.casebook.find_by_complaint_no("TS-2026-0001")))

    def test_same_number_different_facts_opens_separate_case(self) -> None:
        first = self.file(make_complaint())
        by_amount = self.file(make_complaint(amount="2380.00"))
        by_contract = self.file(make_complaint(contract="hash-contract-999"))
        by_material = self.file(make_complaint(materials=("mat-fp-1", "mat-fp-3")))
        for receipt in (by_amount, by_contract, by_material):
            self.assertFalse(receipt.reused)
            self.assertNotEqual(first.case_id, receipt.case_id)
        cases = self.casebook.find_by_complaint_no("TS-2026-0001")
        self.assertEqual(4, len(cases))  # 同号不同事实，单独核查

    def test_narrative_only_difference_still_reuses_receipt(self) -> None:
        complaint = make_complaint()
        first = self.file(complaint)
        from dataclasses import replace

        reworded = replace(complaint, narrative="补充说明：商家态度恶劣")
        again = self.file(reworded)
        self.assertTrue(again.reused)  # 叙述措辞变化不构成新事实

    def test_concurrent_identical_filings_open_one_case(self) -> None:
        results = []
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()
            results.append(self.file(make_complaint()))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(1, len({receipt.case_id for receipt in results}))
        self.assertEqual(1, len({receipt.receipt_no for receipt in results}))
        self.assertEqual(1, len(self.casebook.find_by_complaint_no("TS-2026-0001")))


if __name__ == "__main__":
    unittest.main()
