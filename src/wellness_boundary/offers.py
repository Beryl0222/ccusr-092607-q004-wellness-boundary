"""服务包版本与价格构成登记。

同一服务包的版本号从 1 开始递增，历史版本不可改写，
以便争议发生时还原当时销售的服务内容。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .clock import require_aware
from .registry import ServiceCategory


@dataclass(frozen=True)
class PriceComponent:
    """价格构成中的一项，金额以分为单位。"""

    item: str
    amount_cents: int


@dataclass(frozen=True)
class OfferPackage:
    """服务包的一个版本。"""

    offer_id: str
    version: int
    provider_ref: str
    category: ServiceCategory
    price: tuple[PriceComponent, ...]
    effective_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.effective_at, "版本生效时间")
        if self.version < 1:
            raise ValueError("版本号必须从 1 开始")

    @property
    def total_cents(self) -> int:
        return sum(component.amount_cents for component in self.price)


class OfferCatalog:
    def __init__(self) -> None:
        self._offers: dict[str, list[OfferPackage]] = {}

    def publish(self, package: OfferPackage) -> OfferPackage:
        versions = self._offers.setdefault(package.offer_id, [])
        expected = len(versions) + 1
        if package.version != expected:
            raise ValueError(f"服务包版本号必须递增：期望 {expected}，收到 {package.version}")
        versions.append(package)
        return package

    def version(self, offer_id: str, version: int) -> OfferPackage:
        versions = self._offers.get(offer_id, [])
        if not 1 <= version <= len(versions):
            raise KeyError(f"服务包 {offer_id} 不存在版本 {version}")
        return versions[version - 1]

    def current(self, offer_id: str) -> OfferPackage:
        versions = self._offers.get(offer_id, [])
        if not versions:
            raise KeyError(f"服务包未登记: {offer_id}")
        return versions[-1]
