"""测试共用的构造器。"""

import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wellness_boundary import (  # noqa: E402
    CaseBook,
    ChainLink,
    ClaimClass,
    Complaint,
    ManualClock,
    MarketingClaim,
    PartyRole,
    ProviderProfile,
    Qualification,
    QualificationKind,
)
from wellness_boundary.contracts import validate_event  # noqa: E402

CST = timezone(timedelta(hours=8))
T0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=CST)


def load_schema() -> dict:
    return json.loads((ROOT / "contracts/domain.schema.json").read_text(encoding="utf-8"))


def make_validator():
    schema = load_schema()
    return lambda event: validate_event(event, schema)


def make_casebook(clock: ManualClock | None = None) -> tuple[CaseBook, ManualClock]:
    clock = clock or ManualClock(T0)
    return CaseBook(clock, event_validator=make_validator()), clock


def make_provider(
    ref: str = "mer-001",
    kinds: tuple[str, ...] = ("wellness_operation",),
    name: str = "云栖疗愈工作室",
) -> ProviderProfile:
    qualifications = [
        Qualification(
            kind=QualificationKind(kind),
            certificate_no=f"CERT-{kind}-001",
            issuer="省监管局",
            valid_from=T0 - timedelta(days=400),
        )
        for kind in kinds
    ]
    return ProviderProfile(
        provider_ref=ref,
        name=name,
        regions=("浙江杭州",),
        qualifications=qualifications,
    )


def make_chain() -> list[ChainLink]:
    """一单跨三个地区、三个经营方。"""
    return [
        ChainLink(party_ref="mer-001", role=PartyRole.SELLER, region="浙江杭州"),
        ChainLink(party_ref="plat-001", role=PartyRole.PLATFORM, region="上海"),
        ChainLink(party_ref="sub-001", role=PartyRole.SUBCONTRACTOR, region="四川成都"),
    ]


def make_parties() -> list[ProviderProfile]:
    return [
        make_provider("mer-001", ("wellness_operation",), "云栖疗愈工作室"),
        make_provider("plat-001", ("wellness_operation",), "山海平台"),
        make_provider("sub-001", ("wellness_operation",), "川西履约中心"),
    ]


def make_complaint(
    no: str = "TS-2026-0001",
    amount: str = "1280.00",
    contract: str = "hash-contract-001",
    materials: tuple[str, ...] = ("mat-fp-1", "mat-fp-2"),
) -> Complaint:
    return Complaint(
        complaint_no=no,
        consumer_id="consumer-1",
        order_ref="order-1",
        contract_snapshot_hash=contract,
        amount=Decimal(amount),
        currency="CNY",
        material_fingerprints=materials,
        narrative="宣传可治愈焦虑，实际只是普通冥想课",
        filed_at=T0,
    )


def make_claim(
    claim_id: str = "claim-1",
    merchant_ref: str = "mer-001",
    claim_class: ClaimClass = ClaimClass.MEDICAL_TREATMENT,
    text: str = "七天疗愈焦虑，替代药物治疗",
) -> MarketingClaim:
    return MarketingClaim(
        claim_id=claim_id,
        offer_id="offer-1",
        offer_version=1,
        merchant_ref=merchant_ref,
        claim_class=claim_class,
        text=text,
        evidence=[],
        reviews=[],
        created_at=T0,
    )
