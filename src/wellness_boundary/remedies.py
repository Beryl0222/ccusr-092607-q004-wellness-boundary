"""资金操作台账：冻结、退款、保证金扣划的并发幂等。

- 同一幂等键重复提交且内容一致 → 返回首次记录（``replayed=True``），不重复执行；
- 同一幂等键但内容不同 → 拒绝（``RemedyConflictError``），防止键被挪用；
- 每类操作可设额度上限（退款不超过实收、扣划不超过保证金），超额拒绝；
- 每个案卷一把锁，并发提交在同一案卷内串行化，重复请求不会双双入账。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum

from .clock import Clock
from .errors import BalanceExceededError, DomainError, RemedyConflictError


class RemedyKind(str, Enum):
    FREEZE = "freeze"  # 冻结
    REFUND = "refund"  # 退款
    DEPOSIT_DEDUCTION = "deposit_deduction"  # 保证金扣划


@dataclass(frozen=True)
class RemedyOperation:
    idempotency_key: str
    case_id: str
    kind: RemedyKind
    obligor_ref: str
    amount: Decimal
    currency: str
    reason: str


@dataclass(frozen=True)
class RemedyRecord:
    idempotency_key: str
    case_id: str
    kind: RemedyKind
    obligor_ref: str
    amount: Decimal
    currency: str
    reason: str
    applied_at: datetime
    sequence: int
    replayed: bool = False

    def matches(self, operation: RemedyOperation) -> bool:
        return (
            self.kind is operation.kind
            and self.obligor_ref == operation.obligor_ref
            and self.amount == operation.amount
            and self.currency == operation.currency
            and self.reason == operation.reason
        )


class RemedyLedger:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._records: dict[tuple[str, str], RemedyRecord] = {}
        self._by_case: dict[str, list[RemedyRecord]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._totals: dict[str, dict[RemedyKind, Decimal]] = {}
        self._limits: dict[tuple[str, RemedyKind], Decimal] = {}
        self._meta = threading.Lock()
        self._sequence = 0

    def set_limit(self, case_id: str, kind: RemedyKind, amount: Decimal) -> None:
        """设置案卷级额度上限，例如退款不超过实收、扣划不超过保证金。"""
        if amount <= 0:
            raise DomainError("额度上限必须为正")
        self._limits[(case_id, kind)] = amount

    def _lock_for(self, case_id: str) -> threading.Lock:
        with self._meta:
            self._totals.setdefault(case_id, {})
            self._by_case.setdefault(case_id, [])
            return self._locks.setdefault(case_id, threading.Lock())

    def execute(self, operation: RemedyOperation) -> RemedyRecord:
        if operation.amount <= 0:
            raise DomainError("操作金额必须为正")
        key = (operation.case_id, operation.idempotency_key)
        lock = self._lock_for(operation.case_id)
        with lock:
            existing = self._records.get(key)
            if existing is not None:
                if existing.matches(operation):
                    return replace(existing, replayed=True)
                raise RemedyConflictError("同一幂等键提交了不同的操作内容")
            totals = self._totals[operation.case_id]
            limit = self._limits.get((operation.case_id, operation.kind))
            if limit is not None and totals.get(operation.kind, Decimal("0")) + operation.amount > limit:
                raise BalanceExceededError("超出该案卷此类操作的可执行额度")
            self._sequence += 1
            record = RemedyRecord(
                idempotency_key=operation.idempotency_key,
                case_id=operation.case_id,
                kind=operation.kind,
                obligor_ref=operation.obligor_ref,
                amount=operation.amount,
                currency=operation.currency,
                reason=operation.reason,
                applied_at=self._clock.now(),
                sequence=self._sequence,
            )
            self._records[key] = record
            self._by_case[operation.case_id].append(record)
            totals[operation.kind] = totals.get(operation.kind, Decimal("0")) + operation.amount
            return record

    def total(self, case_id: str, kind: RemedyKind) -> Decimal:
        lock = self._lock_for(case_id)
        with lock:
            return self._totals[case_id].get(kind, Decimal("0"))

    def records_for_case(self, case_id: str) -> list[RemedyRecord]:
        lock = self._lock_for(case_id)
        with lock:
            return sorted(self._by_case[case_id], key=lambda record: record.sequence)
