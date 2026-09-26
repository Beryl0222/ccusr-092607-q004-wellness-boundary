"""投诉登记：重复投诉沿用原回执，材料不同则单独核查。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .clock import require_aware


@dataclass(frozen=True)
class ComplaintFingerprint:
    """投诉材料指纹：合同、金额与材料摘要共同确定一次投诉指向的对象。"""

    contract_ref: str
    amount_cents: int
    material_hash: str


@dataclass
class ComplaintCase:
    receipt_no: str
    complaint_no: str
    fingerprint: ComplaintFingerprint
    opened_at: datetime
    linked_to: str | None = None  # 单独核查时指向同一投诉号下的原回执
    duplicates: int = 0


class ComplaintDesk:
    def __init__(self) -> None:
        self._by_no: dict[str, list[ComplaintCase]] = {}
        self._seq = 0

    def file(self, complaint_no: str, fingerprint: ComplaintFingerprint, at: datetime) -> tuple[ComplaintCase, str]:
        """登记投诉，返回（回执, 结果）。

        结果为 "duplicate"：投诉号与材料指纹都相同，重复投诉沿用原回执；
        结果为 "split"：投诉号相同但合同、金额或材料指纹不同，单独核查并关联原回执；
        结果为 "new"：新投诉。
        """
        require_aware(at, "投诉时间")
        if not complaint_no or not complaint_no.strip():
            raise ValueError("投诉号不能为空")
        cases = self._by_no.setdefault(complaint_no, [])
        for case in cases:
            if case.fingerprint == fingerprint:
                case.duplicates += 1
                return case, "duplicate"
        self._seq += 1
        case = ComplaintCase(
            receipt_no=f"R-{self._seq:06d}",
            complaint_no=complaint_no,
            fingerprint=fingerprint,
            opened_at=at,
            linked_to=cases[0].receipt_no if cases else None,
        )
        outcome = "split" if cases else "new"
        cases.append(case)
        return case, outcome

    def cases_for(self, complaint_no: str) -> list[ComplaintCase]:
        return list(self._by_no.get(complaint_no, []))
