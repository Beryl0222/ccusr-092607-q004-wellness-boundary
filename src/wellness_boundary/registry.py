"""经营主体、从业资质与审查人员登记。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .clock import require_aware


class ServiceCategory(Enum):
    """服务类别，对应监管关注的边界层级。"""

    GENERAL_EXPERIENCE = "general_experience"      # 普通体验
    PSYCH_SUPPORT = "psychological_support"        # 心理支持
    MEDICAL_TREATMENT = "medical_treatment"        # 医疗诊疗


#: 各类别所需的从业资质；普通体验不设资质门槛。
REQUIRED_QUALIFICATION: dict[ServiceCategory, str | None] = {
    ServiceCategory.GENERAL_EXPERIENCE: None,
    ServiceCategory.PSYCH_SUPPORT: "psychological_support",
    ServiceCategory.MEDICAL_TREATMENT: "medical_practice",
}


@dataclass(frozen=True)
class Qualification:
    """从业资质，含发证方与有效期。"""

    kind: str
    issuer: str
    valid_from: datetime
    valid_until: datetime | None = None

    def __post_init__(self) -> None:
        require_aware(self.valid_from, "资质生效时间")
        if self.valid_until is not None:
            require_aware(self.valid_until, "资质失效时间")

    def effective(self, at: datetime) -> bool:
        require_aware(at, "判断时点")
        if at < self.valid_from:
            return False
        return self.valid_until is None or at <= self.valid_until


@dataclass(frozen=True)
class BusinessEntity:
    """经营主体：登记经营地区与从业资质。"""

    entity_id: str
    name: str
    regions: frozenset[str]
    qualifications: tuple[Qualification, ...] = ()

    def holds(self, kind: str, at: datetime) -> bool:
        return any(q.kind == kind and q.effective(at) for q in self.qualifications)

    def permits(self, category: ServiceCategory, at: datetime) -> bool:
        """该主体在指定时点是否被许可提供此类服务。"""
        required = REQUIRED_QUALIFICATION[category]
        return required is None or self.holds(required, at)


class ReviewRole(Enum):
    PLATFORM = "platform"          # 平台审核：只能确认上架信息
    PROFESSIONAL = "professional"  # 专业审查：负责风险边界
    MERCHANT = "merchant"          # 商家：不得批准自己的功效表述


@dataclass(frozen=True)
class Reviewer:
    """审查人员；org_id 用于利益冲突判断。"""

    reviewer_id: str
    role: ReviewRole
    org_id: str


class Registry:
    """主体与审查人员名册。"""

    def __init__(self) -> None:
        self._entities: dict[str, BusinessEntity] = {}
        self._reviewers: dict[str, Reviewer] = {}

    def register_entity(self, entity: BusinessEntity) -> None:
        self._entities[entity.entity_id] = entity

    def entity(self, entity_id: str) -> BusinessEntity:
        try:
            return self._entities[entity_id]
        except KeyError:
            raise KeyError(f"经营主体未登记: {entity_id}") from None

    def register_reviewer(self, reviewer: Reviewer) -> None:
        self._reviewers[reviewer.reviewer_id] = reviewer

    def reviewer(self, reviewer_id: str) -> Reviewer:
        try:
            return self._reviewers[reviewer_id]
        except KeyError:
            raise KeyError(f"审查人员未登记: {reviewer_id}") from None
