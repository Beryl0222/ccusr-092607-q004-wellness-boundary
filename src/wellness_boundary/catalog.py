"""经营主体、从业资质、服务包版本、宣传主张与价格构成。

宣传主张按 ``ClaimClass`` 分级：普通体验 < 心理支持 < 医疗诊疗。
经营主体的许可上限由其在宣传时点有效的从业资质决定；宣传分级超过许可
上限即视为越过合规边界（``claim_exceeds_license``）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum

from .clock import ensure_aware


class ClaimClass(str, Enum):
    GENERAL_EXPERIENCE = "general_experience"  # 普通体验
    PSYCHOLOGICAL_SUPPORT = "psychological_support"  # 心理支持
    MEDICAL_TREATMENT = "medical_treatment"  # 医疗诊疗


CLAIM_RANK = {
    ClaimClass.GENERAL_EXPERIENCE: 1,
    ClaimClass.PSYCHOLOGICAL_SUPPORT: 2,
    ClaimClass.MEDICAL_TREATMENT: 3,
}


class QualificationKind(str, Enum):
    WELLNESS_OPERATION = "wellness_operation"  # 一般经营备案
    PSYCHOLOGICAL_SUPPORT_PERMIT = "psychological_support_permit"  # 心理支持服务许可
    MEDICAL_INSTITUTION_LICENSE = "medical_institution_license"  # 医疗机构执业许可


QUALIFICATION_CEILING = {
    QualificationKind.WELLNESS_OPERATION: ClaimClass.GENERAL_EXPERIENCE,
    QualificationKind.PSYCHOLOGICAL_SUPPORT_PERMIT: ClaimClass.PSYCHOLOGICAL_SUPPORT,
    QualificationKind.MEDICAL_INSTITUTION_LICENSE: ClaimClass.MEDICAL_TREATMENT,
}


@dataclass(frozen=True)
class Qualification:
    kind: QualificationKind
    certificate_no: str
    issuer: str
    valid_from: datetime
    valid_until: datetime | None = None

    def covers(self, at: datetime) -> bool:
        at = ensure_aware(at, "at")
        if at < ensure_aware(self.valid_from, "valid_from"):
            return False
        return self.valid_until is None or at < ensure_aware(self.valid_until, "valid_until")


@dataclass
class ProviderProfile:
    """经营主体与从业资质。"""

    provider_ref: str
    name: str
    regions: tuple[str, ...] = ()
    qualifications: list[Qualification] = field(default_factory=list)

    def ceiling(self, at: datetime | None = None) -> ClaimClass:
        return qualification_ceiling(self, at)


@dataclass(frozen=True)
class PriceItem:
    label: str
    amount: Decimal


@dataclass(frozen=True)
class PriceBreakdown:
    """价格构成：逐项列示，总额由明细加总。"""

    currency: str
    items: tuple[PriceItem, ...]

    @property
    def total(self) -> Decimal:
        return sum((item.amount for item in self.items), Decimal("0"))


@dataclass
class Evidence:
    evidence_id: str
    sha256: str
    kind: str  # screenshot / recording / contract / chat_log ...
    submitted_by: str
    submitted_at: datetime
    restricted: bool = False


@dataclass
class OfferVersion:
    """服务包版本。"""

    offer_id: str
    version: int
    title: str
    service_items: tuple[str, ...]
    price: PriceBreakdown
    effective_from: datetime


@dataclass
class MarketingClaim:
    """宣传主张及其证据。"""

    claim_id: str
    offer_id: str
    offer_version: int
    merchant_ref: str
    claim_class: ClaimClass
    text: str
    created_at: datetime
    evidence: list[Evidence] = field(default_factory=list)
    reviews: list[object] = field(default_factory=list)  # ReviewDecision，避免循环依赖


def qualification_ceiling(profile: ProviderProfile, at: datetime | None = None) -> ClaimClass:
    """主体在指定时点有效的最高许可分级；无任何有效资质时仅允许普通体验。"""
    ceiling = ClaimClass.GENERAL_EXPERIENCE
    for qualification in profile.qualifications:
        if at is not None and not qualification.covers(at):
            continue
        qualified = QUALIFICATION_CEILING[qualification.kind]
        if CLAIM_RANK[qualified] > CLAIM_RANK[ceiling]:
            ceiling = qualified
    return ceiling


def claim_exceeds_license(
    profile: ProviderProfile,
    claim: MarketingClaim,
    at: datetime | None = None,
) -> bool:
    """宣传分级是否超出主体在宣传时点的许可上限。"""
    moment = at if at is not None else claim.created_at
    return CLAIM_RANK[claim.claim_class] > CLAIM_RANK[qualification_ceiling(profile, moment)]
