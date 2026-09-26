"""版本化规则集：处理决定必须落在作出时点有效的规则上。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .clock import ensure_aware
from .errors import RuleVersionError


@dataclass(frozen=True)
class RuleSet:
    rule_version: str
    effective_from: datetime
    effective_until: datetime | None
    summary: str
    provisions: tuple[str, ...] = ()

    def covers(self, at: datetime) -> bool:
        at = ensure_aware(at, "at")
        if at < ensure_aware(self.effective_from, "effective_from"):
            return False
        return self.effective_until is None or at < ensure_aware(
            self.effective_until, "effective_until"
        )


class RuleBook:
    def __init__(self) -> None:
        self._sets: dict[str, RuleSet] = {}

    def register(self, rule_set: RuleSet) -> None:
        if rule_set.rule_version in self._sets:
            raise RuleVersionError(f"规则版本重复登记：{rule_set.rule_version}")
        self._sets[rule_set.rule_version] = rule_set

    def get(self, rule_version: str) -> RuleSet:
        try:
            return self._sets[rule_version]
        except KeyError:
            raise RuleVersionError(f"规则版本未登记：{rule_version}") from None

    def effective_at(self, at: datetime) -> RuleSet:
        candidates = [rule_set for rule_set in self._sets.values() if rule_set.covers(at)]
        if not candidates:
            raise RuleVersionError("该时点没有有效规则")
        return max(candidates, key=lambda rule_set: rule_set.effective_from)
