"""案卷服务层领域错误。

每个错误都携带稳定的 ``code``，便于上层接口映射与对账。
"""

from __future__ import annotations


class DomainError(Exception):
    """服务层所有领域错误的基类。"""

    code = "domain_error"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.code
        super().__init__(self.message)


class ContractViolationError(DomainError):
    code = "contract_violation"


class EventConflictError(DomainError):
    code = "event_conflict"


class CaseNotFoundError(DomainError):
    code = "case_not_found"


class ClaimNotFoundError(DomainError):
    code = "claim_not_found"


class ConsentNotFoundError(DomainError):
    code = "consent_not_found"


class ObligationNotFoundError(DomainError):
    code = "obligation_not_found"


class DeadlineNotFoundError(DomainError):
    code = "deadline_not_found"


class DeadlineStateError(DomainError):
    code = "deadline_state"


class DuplicateRegistrationError(DomainError):
    code = "duplicate_registration"


class ReviewPermissionError(DomainError):
    code = "review_permission"


class SelfApprovalError(ReviewPermissionError):
    code = "self_approval"


class ConsentWithdrawnError(DomainError):
    code = "consent_withdrawn"


class RemedyConflictError(DomainError):
    code = "remedy_conflict"


class BalanceExceededError(DomainError):
    code = "balance_exceeded"


class ObligationStateError(DomainError):
    code = "obligation_state"


class RuleVersionError(DomainError):
    code = "rule_version"


class DispositionStateError(DomainError):
    code = "disposition_state"


class AccessDeniedError(DomainError):
    code = "access_denied"
