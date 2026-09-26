"""宣传主张登记与审查职责分离。

平台审核只能确认上架信息；风险边界由专业审查决定；
商家及其所属机构的人员不得批准自己的功效表述。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .clock import require_aware
from .registry import Registry, ReviewRole, ServiceCategory


class ClaimStatus(Enum):
    SUBMITTED = "submitted"                    # 已提交，待平台确认
    LISTING_CONFIRMED = "listing_confirmed"    # 平台已确认上架信息
    APPROVED = "approved"                      # 专业审查认定未越界
    REJECTED = "rejected"                      # 专业审查认定越界


@dataclass
class Claim:
    """一条宣传主张及其证据材料。"""

    claim_id: str
    merchant_ref: str
    offer_ref: str
    category: ServiceCategory
    statement: str
    evidence_refs: tuple[str, ...]
    submitted_at: datetime
    status: ClaimStatus = ClaimStatus.SUBMITTED
    reviewer_ref: str | None = None
    rule_version: str | None = None

    def __post_init__(self) -> None:
        require_aware(self.submitted_at, "宣传提交时间")


class ClaimDesk:
    """宣传审查台：保证平台、专业审查与商家之间的职责分离。"""

    def __init__(self, registry: Registry) -> None:
        self._registry = registry
        self._claims: dict[str, Claim] = {}

    def submit(self, claim: Claim) -> Claim:
        if claim.claim_id in self._claims:
            raise ValueError(f"宣传主张已登记: {claim.claim_id}")
        self._registry.entity(claim.merchant_ref)  # 经营主体必须先登记
        self._claims[claim.claim_id] = claim
        return claim

    def get(self, claim_id: str) -> Claim:
        try:
            return self._claims[claim_id]
        except KeyError:
            raise KeyError(f"宣传主张未登记: {claim_id}") from None

    def all(self) -> list[Claim]:
        return list(self._claims.values())

    def confirm_listing(self, claim_id: str, reviewer_id: str, at: datetime) -> Claim:
        """平台审核只能确认上架信息，不能决定风险边界。"""
        require_aware(at, "确认时间")
        reviewer = self._registry.reviewer(reviewer_id)
        if reviewer.role is not ReviewRole.PLATFORM:
            raise PermissionError("上架信息只能由平台审核确认")
        claim = self.get(claim_id)
        if claim.status is not ClaimStatus.SUBMITTED:
            raise ValueError("只有待确认的宣传才能确认上架")
        claim.status = ClaimStatus.LISTING_CONFIRMED
        return claim

    def review_boundary(
        self,
        claim_id: str,
        reviewer_id: str,
        approve: bool,
        rule_version: str,
        at: datetime,
    ) -> Claim:
        """专业审查决定风险边界；商家不得批准自己的功效表述。"""
        require_aware(at, "审查时间")
        if not rule_version or not rule_version.strip():
            raise ValueError("审查必须记录当时有效的规则版本")
        claim = self.get(claim_id)
        reviewer = self._registry.reviewer(reviewer_id)
        if reviewer.role is ReviewRole.MERCHANT or reviewer.org_id == claim.merchant_ref:
            raise PermissionError("商家不得批准自己的功效表述")
        if reviewer.role is not ReviewRole.PROFESSIONAL:
            raise PermissionError("风险边界只能由专业审查决定")
        if claim.status is not ClaimStatus.LISTING_CONFIRMED:
            raise ValueError("上架信息未确认前不能进行边界审查")
        claim.status = ClaimStatus.APPROVED if approve else ClaimStatus.REJECTED
        claim.reviewer_ref = reviewer_id
        claim.rule_version = rule_version
        return claim

    def exceeds_license(self, claim_id: str, at: datetime) -> bool:
        """宣传类别是否超出经营主体在指定时点的许可范围。"""
        claim = self.get(claim_id)
        entity = self._registry.entity(claim.merchant_ref)
        return not entity.permits(claim.category, at)
