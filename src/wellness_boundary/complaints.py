"""投诉受理：指纹去重与单独核查。

- 同一投诉号、且合同快照、金额与材料指纹完全一致 → 重复投诉，沿用原回执；
- 投诉号相同但合同、金额或材料指纹任一不同 → 视为不同事实，单独核查开新案卷；
- 受理过程加锁，并发提交同一投诉不会开出两本案卷。
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:  # pragma: no cover
    from .casefile import CaseBook, CaseFile, ChainLink
    from .catalog import ProviderProfile
    from .clock import Clock


@dataclass(frozen=True)
class Complaint:
    complaint_no: str
    consumer_id: str
    order_ref: str
    contract_snapshot_hash: str
    amount: Decimal
    currency: str
    material_fingerprints: tuple[str, ...]
    narrative: str
    filed_at: datetime


def complaint_fingerprint(complaint: Complaint) -> str:
    """以合同快照、金额与材料指纹计算事实指纹（不含叙述文本）。"""
    canonical = json.dumps(
        {
            "contract": complaint.contract_snapshot_hash,
            "amount": str(complaint.amount),
            "currency": complaint.currency,
            "materials": sorted(complaint.material_fingerprints),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Receipt:
    receipt_no: str
    case_id: str
    complaint_no: str
    issued_at: datetime
    reused: bool  # True 表示重复投诉沿用了原回执


class ComplaintService:
    def __init__(self, casebook: "CaseBook", clock: "Clock") -> None:
        self._casebook = casebook
        self._clock = clock
        self._lock = threading.Lock()

    def file(
        self,
        complaint: Complaint,
        *,
        chain: "Iterable[ChainLink]" = (),
        parties: "Iterable[ProviderProfile]" = (),
    ) -> Receipt:
        fingerprint = complaint_fingerprint(complaint)
        with self._lock:
            for case in self._casebook.find_by_complaint_no(complaint.complaint_no):
                if case.fingerprint == fingerprint:
                    case.duplicate_filings += 1
                    return Receipt(
                        receipt_no=case.receipt_no,
                        case_id=case.case_id,
                        complaint_no=case.complaint_no,
                        issued_at=case.opened_at,
                        reused=True,
                    )
            case = self._casebook.open_case(
                complaint,
                fingerprint=fingerprint,
                chain=chain,
                parties=parties,
            )
            return Receipt(
                receipt_no=case.receipt_no,
                case_id=case.case_id,
                complaint_no=case.complaint_no,
                issued_at=case.opened_at,
                reused=False,
            )

    def case_of(self, receipt: Receipt) -> "CaseFile":
        return self._casebook.get(receipt.case_id)
