"""测试共用的登记夹具。"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wellness_boundary.registry import (  # noqa: E402
    BusinessEntity,
    Qualification,
    Registry,
    Reviewer,
    ReviewRole,
)

TZ = timezone(timedelta(hours=8))
T0 = datetime(2026, 9, 20, 10, 0, tzinfo=TZ)


def qual(kind: str, valid_days: int = 365) -> Qualification:
    return Qualification(
        kind=kind,
        issuer="监管机构",
        valid_from=T0 - timedelta(days=30),
        valid_until=T0 + timedelta(days=valid_days),
    )


def build_registry() -> Registry:
    registry = Registry()
    registry.register_entity(BusinessEntity(
        entity_id="merchant-1",
        name="静修文旅",
        regions=frozenset({"浙江", "海南"}),
        qualifications=(qual("psychological_support"),),
    ))
    registry.register_entity(BusinessEntity(
        entity_id="merchant-2",
        name="云疗愈科技",
        regions=frozenset({"上海"}),
        qualifications=(),
    ))
    registry.register_entity(BusinessEntity(
        entity_id="sub-1",
        name="山野营地",
        regions=frozenset({"云南"}),
        qualifications=(),
    ))
    registry.register_reviewer(Reviewer("rev-platform", ReviewRole.PLATFORM, "platform-1"))
    registry.register_reviewer(Reviewer("rev-pro", ReviewRole.PROFESSIONAL, "expert-org"))
    registry.register_reviewer(Reviewer("rev-pro-captured", ReviewRole.PROFESSIONAL, "merchant-1"))
    registry.register_reviewer(Reviewer("rev-merchant", ReviewRole.MERCHANT, "merchant-1"))
    return registry
