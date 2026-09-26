"""查询视图：监管接口、消费者查询与最终处理追溯。

- 监管视图：每条宣传是否超出许可、各方尚未履行什么义务、期限与证据全貌；
- 消费者视图：最小必要案情与明确责任方，不暴露内部审查意见与他人材料；
- 追溯视图：从最终处理回到当时有效的规则版本与完整证据链、事件链。
"""

from __future__ import annotations

from .casefile import CaseBook, CaseFile, Obligation, PartyRole
from .catalog import claim_exceeds_license, qualification_ceiling
from .errors import AccessDeniedError, DispositionStateError
from .remedies import RemedyKind
from .reviews import ReviewOutcome, ReviewScope
from .rules import RuleBook


def _deadline_brief(casebook: CaseBook, obligation: Obligation) -> dict | None:
    if obligation.deadline_id is None:
        return None
    deadline = casebook.deadlines.get(obligation.deadline_id)
    now = casebook.clock.now()
    return {
        "deadline_id": deadline.deadline_id,
        "kind": deadline.kind.value,
        "status": deadline.status.value,
        "remaining_seconds": deadline.remaining(now).total_seconds(),
        "expired": deadline.is_expired(now),
    }


def _obligation_brief(casebook: CaseBook, obligation: Obligation) -> dict:
    return {
        "obligation_id": obligation.obligation_id,
        "kind": obligation.kind.value,
        "obligor_ref": obligation.obligor_ref,
        "delegated_to": obligation.delegated_to,
        "description": obligation.description,
        "deadline": _deadline_brief(casebook, obligation),
    }


def regulator_view(casebook: CaseBook, case_id: str) -> dict:
    """监管接口：宣传越界判定与各方未履行义务。"""
    case = casebook.get(case_id)
    now = casebook.clock.now()
    claims = []
    for claim in case.claims.values():
        provider = case.parties.get(claim.merchant_ref)
        ceiling = qualification_ceiling(provider, claim.created_at) if provider else None
        boundary = _latest_review(claim, ReviewScope.RISK_BOUNDARY)
        listing = _latest_review(claim, ReviewScope.LISTING)
        claims.append(
            {
                "claim_id": claim.claim_id,
                "merchant_ref": claim.merchant_ref,
                "claim_class": claim.claim_class.value,
                "text": claim.text,
                "permitted_ceiling": ceiling.value if ceiling else None,
                "exceeds_license": (
                    claim_exceeds_license(provider, claim) if provider else None
                ),
                "boundary_review": boundary.outcome.value if boundary else None,
                "listing_confirmed": bool(
                    listing and listing.outcome is ReviewOutcome.APPROVED
                ),
            }
        )
    outstanding = case.outstanding_obligations()
    by_party: dict[str, list[dict]] = {}
    for obligation in outstanding:
        brief = _obligation_brief(casebook, obligation)
        by_party.setdefault(obligation.obligor_ref, []).append(brief)
    return {
        "case_id": case.case_id,
        "complaint_no": case.complaint_no,
        "status": case.status.value,
        "claims": claims,
        "outstanding_obligations": [_obligation_brief(casebook, o) for o in outstanding],
        "obligations_by_party": by_party,
        "responsibility_chain": _chain_brief(case, by_party),
        "deadlines": [
            {
                "deadline_id": deadline.deadline_id,
                "kind": deadline.kind.value,
                "status": deadline.status.value,
                "remaining_seconds": deadline.remaining(now).total_seconds(),
                "expired": deadline.is_expired(now),
            }
            for deadline in casebook.deadlines.for_case(case.case_id)
        ],
        "evidence": _evidence_brief(case),
        "remedies": [
            {
                "kind": record.kind.value,
                "obligor_ref": record.obligor_ref,
                "amount": str(record.amount),
                "currency": record.currency,
                "applied_at": record.applied_at.isoformat(),
            }
            for record in casebook.remedies.records_for_case(case.case_id)
        ],
    }


def consumer_view(casebook: CaseBook, case_id: str, consumer_id: str) -> dict:
    """消费者查询：最小必要案情与明确责任方。"""
    case = casebook.get(case_id)
    if case.consumer_id != consumer_id:
        raise AccessDeniedError("只能查询本人案卷")
    seller = next(
        (link for link in case.chain if link.role is PartyRole.SELLER),
        case.chain[0] if case.chain else None,
    )
    responsible = None
    if seller is not None:
        profile = case.parties.get(seller.party_ref)
        responsible = {
            "party_ref": seller.party_ref,
            "name": profile.name if profile else seller.party_ref,
            "role": seller.role.value,
        }
    refunds = [
        {"amount": str(record.amount), "currency": record.currency, "applied_at": record.applied_at.isoformat()}
        for record in casebook.remedies.records_for_case(case.case_id)
        if record.kind is RemedyKind.REFUND
    ]
    view = {
        "case_id": case.case_id,
        "receipt_no": case.receipt_no,
        "status": case.status.value,
        "responsible_party": responsible,
        "pending_obligations": [
            {
                "kind": obligation.kind.value,
                "obligor_ref": obligation.obligor_ref,
                "deadline": _deadline_brief(casebook, obligation),
            }
            for obligation in case.outstanding_obligations()
        ],
        "refunds": refunds,
    }
    if case.disposition is not None:
        view["disposition"] = {
            "summary": case.disposition.summary,
            "decided_at": case.disposition.decided_at.isoformat(),
        }
    return view


def trace_disposition(casebook: CaseBook, case_id: str, rulebook: RuleBook) -> dict:
    """从最终处理追溯当时有效的规则与完整证据链。"""
    case = casebook.get(case_id)
    if case.disposition is None:
        raise DispositionStateError("案卷尚未作出最终处理")
    disposition = case.disposition
    rule_set = rulebook.get(disposition.rule_version)
    effective = rulebook.effective_at(disposition.decided_at)
    return {
        "disposition": {
            "disposition_id": disposition.disposition_id,
            "decided_at": disposition.decided_at.isoformat(),
            "decided_by": disposition.decided_by,
            "rule_version": disposition.rule_version,
            "summary": disposition.summary,
        },
        "rule_set": {
            "rule_version": rule_set.rule_version,
            "effective_from": rule_set.effective_from.isoformat(),
            "effective_until": (
                rule_set.effective_until.isoformat() if rule_set.effective_until else None
            ),
            "summary": rule_set.summary,
            "provisions": list(rule_set.provisions),
            "was_effective_at_decision": effective.rule_version == rule_set.rule_version,
        },
        "evidence_chain": _evidence_brief(case),
        "events": [
            {
                "event_id": event["event_id"],
                "event_type": event["event_type"],
                "aggregate_id": event["aggregate_id"],
                "occurred_at": event["occurred_at"],
                "version": event["version"],
            }
            for event in case.events.all()
        ],
    }


def _latest_review(claim, scope: ReviewScope):
    reviews = [review for review in claim.reviews if review.scope is scope]
    return reviews[-1] if reviews else None


def _chain_brief(case: CaseFile, by_party: dict[str, list[dict]]) -> list[dict]:
    return [
        {
            "party_ref": link.party_ref,
            "role": link.role.value,
            "region": link.region,
            "outstanding_count": len(by_party.get(link.party_ref, [])),
        }
        for link in case.chain
    ]


def _evidence_brief(case: CaseFile) -> list[dict]:
    items = []
    for claim in case.claims.values():
        for evidence in claim.evidence:
            items.append(
                {
                    "evidence_id": evidence.evidence_id,
                    "sha256": evidence.sha256,
                    "kind": evidence.kind,
                    "source": f"claim:{claim.claim_id}",
                    "restricted": evidence.restricted,
                }
            )
    for material in case.materials.values():
        items.append(
            {
                "evidence_id": material.material_id,
                "sha256": material.sha256,
                "kind": material.kind,
                "source": f"material:{material.purpose}",
                "restricted": material.access_restricted,
            }
        )
    return items
