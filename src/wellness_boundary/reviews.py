"""宣传审查的权限分离。

- 平台审核只能确认上架信息（``ReviewScope.LISTING``）；
- 专业审查负责风险边界（``ReviewScope.RISK_BOUNDARY``）；
- 商家不得批准自己的功效表述——对自身宣传提交“通过”即被拒绝。

每条审查决定都会以 ``CLAIM_SCREENED`` 事件落入案卷审计链，携带作出决定时
使用的规则版本，供最终处理追溯。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from .errors import ClaimNotFoundError, ReviewPermissionError, SelfApprovalError

if TYPE_CHECKING:  # pragma: no cover
    from .casefile import CaseFile


class ReviewerRole(str, Enum):
    PLATFORM = "platform"  # 平台审核
    PROFESSIONAL = "professional"  # 专业审查
    MERCHANT = "merchant"  # 商家


class ReviewScope(str, Enum):
    LISTING = "listing"  # 上架信息
    RISK_BOUNDARY = "risk_boundary"  # 风险边界


class ReviewOutcome(str, Enum):
    APPROVED = "approved"  # 通过 / 在边界内
    FLAGGED = "flagged"  # 存疑 / 越界


@dataclass(frozen=True)
class Reviewer:
    reviewer_ref: str
    role: ReviewerRole
    merchant_ref: str | None = None  # 商家审核人关联的经营主体


@dataclass(frozen=True)
class ReviewDecision:
    decision_id: str
    claim_id: str
    reviewer_ref: str
    reviewer_role: ReviewerRole
    scope: ReviewScope
    outcome: ReviewOutcome
    rule_version: str
    rationale: str
    decided_at: datetime


_SCOPE_ROLES = {
    ReviewScope.LISTING: ReviewerRole.PLATFORM,
    ReviewScope.RISK_BOUNDARY: ReviewerRole.PROFESSIONAL,
}


def submit_review(
    case: "CaseFile",
    claim_id: str,
    *,
    reviewer: Reviewer,
    scope: ReviewScope,
    outcome: ReviewOutcome,
    rule_version: str,
    rationale: str,
    now: datetime,
) -> ReviewDecision:
    """登记一条审查决定，强制审查权限分离。"""
    claim = case.claims.get(claim_id)
    if claim is None:
        raise ClaimNotFoundError(f"宣传主张不存在：{claim_id}")
    if (
        reviewer.role is ReviewerRole.MERCHANT
        and reviewer.merchant_ref == claim.merchant_ref
        and outcome is ReviewOutcome.APPROVED
    ):
        raise SelfApprovalError("商家不得批准自己的功效表述")
    required_role = _SCOPE_ROLES[scope]
    if reviewer.role is not required_role:
        if scope is ReviewScope.LISTING:
            raise ReviewPermissionError("上架信息只能由平台审核确认")
        raise ReviewPermissionError("风险边界只能由专业审查判定")
    decision = ReviewDecision(
        decision_id=f"{claim_id}-review-{len(claim.reviews) + 1}",
        claim_id=claim_id,
        reviewer_ref=reviewer.reviewer_ref,
        reviewer_role=reviewer.role,
        scope=scope,
        outcome=outcome,
        rule_version=rule_version,
        rationale=rationale,
        decided_at=now,
    )
    claim.reviews.append(decision)
    case.events.record(
        "CLAIM_SCREENED",
        "marketing_claim",
        claim.claim_id,
        now,
        {
            "rule_version": rule_version,
            "review_scope": scope.value,
            "outcome": outcome.value,
            "reviewer_role": reviewer.role.value,
            "claim_class": claim.claim_class.value,
        },
    )
    return decision
