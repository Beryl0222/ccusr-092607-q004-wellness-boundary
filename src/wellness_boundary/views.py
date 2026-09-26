"""监管与消费者的查询视图，以及最终处理的追溯。

监管接口展示每条宣传是否超出许可、各方尚未履行的义务；
消费者查询只获得最小必要案情和明确责任方；
最终处理可以追溯到当时有效的规则与完整证据链。
"""

from __future__ import annotations

from typing import Any

from .casefile import CaseFile
from .consent import Purpose

#: 追溯属于监管调取，即使相关同意已撤回也允许读取证据元数据。
_TRACE_PURPOSE = Purpose.REGULATORY


def regulator_view(case: CaseFile) -> dict[str, Any]:
    """监管视图：宣传合规状态与各方未履行义务。"""
    now = case.clock.now()
    claims = [
        {
            "claim_id": claim.claim_id,
            "merchant_ref": claim.merchant_ref,
            "category": claim.category.value,
            "status": claim.status.value,
            "exceeds_license": case.claims.exceeds_license(claim.claim_id, now),
            "rule_version": claim.rule_version,
        }
        for claim in case.claims.all()
    ]
    outstanding: dict[str, list[str]] = {}
    for obligation in case.obligations.unfulfilled():
        outstanding.setdefault(obligation.obligor_ref, []).append(obligation.obligation_id)
    return {
        "case_id": case.case_id,
        "regions": case.regions,
        "parties": case.parties,
        "claims": claims,
        "unfulfilled_obligations": outstanding,
        "rule_version": case.rule_version,
    }


def consumer_view(case: CaseFile) -> dict[str, Any]:
    """消费者视图：最小必要案情与明确责任方。"""
    responsible = case.registry.entity(case.lead_obligor) if case.lead_obligor else None
    view: dict[str, Any] = {
        "case_id": case.case_id,
        "status": "closed" if case.disposition is not None else "open",
        "responsible_party": (
            {"entity_id": responsible.entity_id, "name": responsible.name} if responsible else None
        ),
    }
    if case.disposition is not None:
        view["outcome"] = case.disposition.outcome
    return view


def trace_disposition(case: CaseFile) -> dict[str, Any]:
    """从最终处理追溯到当时有效的规则版本与完整证据链。"""
    if case.disposition is None:
        raise ValueError("案卷尚未作出最终处理，无法追溯")
    disposition = case.disposition
    evidence_chain = []
    for evidence_hash in disposition.evidence_hashes:
        item = case.vault.access(evidence_hash, _TRACE_PURPOSE, disposition.decided_at)
        evidence_chain.append({
            "evidence_hash": item.evidence_hash,
            "consent_ref": item.consent_ref,
            "collected_at": item.collected_at.isoformat(),
        })
    return {
        "case_id": case.case_id,
        "outcome": disposition.outcome,
        "rule_version": disposition.rule_version,
        "decided_at": disposition.decided_at.isoformat(),
        "evidence_chain": evidence_chain,
        "event_trail": [event["event_id"] for event in case.events],
    }
