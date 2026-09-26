"""冻结、退款与保证金扣划的幂等台账。

每笔资金操作都携带幂等键：相同键重放直接返回原结果，
相同键但参数不同视为冲突；冻结、退款、扣划各自不得超过对应上限，
以此避免并发或重试造成的重复执行。金额一律以分为单位。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .clock import require_aware


class FundsOpKind(Enum):
    FREEZE = "freeze"                    # 冻结
    REFUND = "refund"                    # 退款
    DEPOSIT_DEDUCT = "deposit_deduct"    # 保证金扣划


@dataclass(frozen=True)
class FundsOperation:
    kind: FundsOpKind
    account_ref: str        # 冻结/退款为订单号，扣划为责任方编号
    amount_cents: int
    idempotency_key: str
    applied_at: datetime


class FundsLedger:
    def __init__(self) -> None:
        self._ops: dict[str, FundsOperation] = {}
        self._paid: dict[str, int] = {}
        self._frozen: dict[str, int] = {}
        self._refunded: dict[str, int] = {}
        self._deposit: dict[str, int] = {}
        self._deducted: dict[str, int] = {}

    def record_payment(self, order_ref: str, amount_cents: int) -> None:
        """登记订单实收，作为冻结与退款的上限。"""
        if amount_cents <= 0:
            raise ValueError("金额必须为正")
        self._paid[order_ref] = self._paid.get(order_ref, 0) + amount_cents

    def record_deposit(self, obligor_ref: str, amount_cents: int) -> None:
        """登记保证金余额，作为扣划的上限。"""
        if amount_cents <= 0:
            raise ValueError("金额必须为正")
        self._deposit[obligor_ref] = self._deposit.get(obligor_ref, 0) + amount_cents

    def _apply(
        self,
        kind: FundsOpKind,
        account_ref: str,
        amount_cents: int,
        idempotency_key: str,
        at: datetime,
    ) -> FundsOperation:
        require_aware(at, "操作时间")
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("资金操作必须携带幂等键")
        existing = self._ops.get(idempotency_key)
        if existing is not None:
            same = (
                existing.kind is kind
                and existing.account_ref == account_ref
                and existing.amount_cents == amount_cents
            )
            if not same:
                raise ValueError("相同幂等键提交了不同的资金操作")
            return existing  # 并发或重试造成的重复，直接返回原结果
        if amount_cents <= 0:
            raise ValueError("金额必须为正")
        if kind is FundsOpKind.FREEZE:
            if self._frozen.get(account_ref, 0) + amount_cents > self._paid.get(account_ref, 0):
                raise ValueError("冻结金额不能超过订单实收")
            self._frozen[account_ref] = self._frozen.get(account_ref, 0) + amount_cents
        elif kind is FundsOpKind.REFUND:
            if self._refunded.get(account_ref, 0) + amount_cents > self._paid.get(account_ref, 0):
                raise ValueError("退款金额不能超过订单实收")
            self._refunded[account_ref] = self._refunded.get(account_ref, 0) + amount_cents
        else:
            if self._deducted.get(account_ref, 0) + amount_cents > self._deposit.get(account_ref, 0):
                raise ValueError("扣划金额不能超过保证金余额")
            self._deducted[account_ref] = self._deducted.get(account_ref, 0) + amount_cents
        op = FundsOperation(
            kind=kind,
            account_ref=account_ref,
            amount_cents=amount_cents,
            idempotency_key=idempotency_key,
            applied_at=at,
        )
        self._ops[idempotency_key] = op
        return op

    def freeze(self, order_ref: str, amount_cents: int, idempotency_key: str, at: datetime) -> FundsOperation:
        return self._apply(FundsOpKind.FREEZE, order_ref, amount_cents, idempotency_key, at)

    def refund(self, order_ref: str, amount_cents: int, idempotency_key: str, at: datetime) -> FundsOperation:
        return self._apply(FundsOpKind.REFUND, order_ref, amount_cents, idempotency_key, at)

    def deduct_deposit(self, obligor_ref: str, amount_cents: int, idempotency_key: str, at: datetime) -> FundsOperation:
        return self._apply(FundsOpKind.DEPOSIT_DEDUCT, obligor_ref, amount_cents, idempotency_key, at)

    def frozen_of(self, order_ref: str) -> int:
        return self._frozen.get(order_ref, 0)

    def refunded_of(self, order_ref: str) -> int:
        return self._refunded.get(order_ref, 0)

    def deducted_of(self, obligor_ref: str) -> int:
        return self._deducted.get(obligor_ref, 0)
