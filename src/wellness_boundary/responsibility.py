"""跨地区、跨经营方的履约责任链。

一次订单可能跨越多个地区和多个经营方；
转包只改变实际履约方，责任仍归原责任方，不能因转包而丢失。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ObligationStatus(Enum):
    PENDING = "pending"
    FULFILLED = "fulfilled"


@dataclass
class Obligation:
    """一项待履行义务；obligor_ref 是责任方，performer_ref 是实际履约方。"""

    obligation_id: str
    order_ref: str
    obligor_ref: str
    description: str
    performer_ref: str | None = None
    status: ObligationStatus = ObligationStatus.PENDING


class ResponsibilityChain:
    def __init__(self) -> None:
        self._obligations: dict[str, Obligation] = {}

    def assign(self, obligation: Obligation) -> Obligation:
        if obligation.obligation_id in self._obligations:
            raise ValueError(f"义务已登记: {obligation.obligation_id}")
        self._obligations[obligation.obligation_id] = obligation
        return obligation

    def get(self, obligation_id: str) -> Obligation:
        try:
            return self._obligations[obligation_id]
        except KeyError:
            raise KeyError(f"义务未登记: {obligation_id}") from None

    def subcontract(self, obligation_id: str, performer_ref: str) -> Obligation:
        """转包给第三方履约；责任方不变。"""
        obligation = self.get(obligation_id)
        if obligation.status is ObligationStatus.FULFILLED:
            raise ValueError("义务已履行，不能再转包")
        if performer_ref == obligation.obligor_ref:
            raise ValueError("责任方自身履约不构成转包")
        obligation.performer_ref = performer_ref
        return obligation

    def fulfill(self, obligation_id: str, by_party: str) -> Obligation:
        """责任方或受转包的履约方都可以履行；履行记录仍挂在责任方名下。"""
        obligation = self.get(obligation_id)
        if obligation.status is ObligationStatus.FULFILLED:
            raise ValueError("义务已履行，不能重复履行")
        if by_party not in {obligation.obligor_ref, obligation.performer_ref}:
            raise PermissionError("只有责任方或登记的履约方可以履行该义务")
        obligation.status = ObligationStatus.FULFILLED
        return obligation

    def responsible_for(self, obligation_id: str) -> str:
        """无论是否转包，责任方始终是 obligor。"""
        return self.get(obligation_id).obligor_ref

    def unfulfilled(self, party_ref: str | None = None) -> list[Obligation]:
        """各方尚未履行的义务；按责任方归集，不按履约方。"""
        pending = [o for o in self._obligations.values() if o.status is ObligationStatus.PENDING]
        if party_ref is not None:
            pending = [o for o in pending if o.obligor_ref == party_ref]
        return sorted(pending, key=lambda o: o.obligation_id)
