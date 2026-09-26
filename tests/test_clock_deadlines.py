import unittest
from datetime import datetime, timedelta

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import T0

from wellness_boundary import (
    DeadlineEngine,
    DeadlineKind,
    DeadlineStatus,
    ManualClock,
)
from wellness_boundary.clock import ensure_aware
from wellness_boundary.errors import DeadlineStateError, DomainError


class ClockTests(unittest.TestCase):
    def test_manual_clock_advances(self) -> None:
        clock = ManualClock(T0)
        clock.advance(timedelta(hours=2))
        self.assertEqual(T0 + timedelta(hours=2), clock.now())

    def test_naive_datetime_rejected(self) -> None:
        with self.assertRaises(DomainError):
            ensure_aware(datetime(2026, 9, 20, 10, 0, 0))
        with self.assertRaises(DomainError):
            ManualClock(datetime(2026, 9, 20, 10, 0, 0))


class DeadlineEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = ManualClock(T0)
        self.engine = DeadlineEngine(self.clock)

    def test_all_kinds_open_with_controllable_clock(self) -> None:
        for kind in DeadlineKind:
            deadline = self.engine.open("CASE-1", kind, timedelta(days=7))
            self.assertEqual(DeadlineStatus.RUNNING, deadline.status)
            self.assertEqual(timedelta(days=7), self.engine.remaining(deadline.deadline_id))
        self.clock.advance(timedelta(days=1))
        self.assertEqual(4, len(self.engine.for_case("CASE-1")))

    def test_non_positive_duration_rejected(self) -> None:
        with self.assertRaises(DomainError):
            self.engine.open("CASE-1", DeadlineKind.REFUND, timedelta(0))

    def test_pause_freezes_and_resume_continues_original_countdown(self) -> None:
        deadline = self.engine.open("CASE-1", DeadlineKind.REFUND, timedelta(days=7))
        self.clock.advance(timedelta(days=2))
        self.engine.pause(deadline.deadline_id, reason="服务暂停")
        # 暂停期间墙钟流逝 10 天，倒计时保持冻结
        self.clock.advance(timedelta(days=10))
        self.assertFalse(self.engine.is_expired(deadline.deadline_id))
        self.assertEqual(timedelta(days=5), self.engine.remaining(deadline.deadline_id))
        self.engine.resume(deadline.deadline_id)
        # 恢复后继续原有倒计时：剩余仍是 5 天
        self.assertEqual(timedelta(days=5), self.engine.remaining(deadline.deadline_id))
        self.clock.advance(timedelta(days=5))
        self.assertTrue(self.engine.is_expired(deadline.deadline_id))

    def test_multiple_pauses_accumulate(self) -> None:
        deadline = self.engine.open("CASE-1", DeadlineKind.RECTIFICATION, timedelta(days=10))
        self.clock.advance(timedelta(days=1))
        self.engine.pause(deadline.deadline_id)
        self.clock.advance(timedelta(days=3))
        self.engine.resume(deadline.deadline_id)
        self.clock.advance(timedelta(days=1))
        self.engine.pause(deadline.deadline_id)
        self.clock.advance(timedelta(days=100))
        self.engine.resume(deadline.deadline_id)
        self.assertEqual(timedelta(days=8), self.engine.remaining(deadline.deadline_id))

    def test_state_transitions_are_guarded(self) -> None:
        deadline = self.engine.open("CASE-1", DeadlineKind.COOLING_OFF, timedelta(days=7))
        with self.assertRaises(DeadlineStateError):
            self.engine.resume(deadline.deadline_id)
        self.engine.pause(deadline.deadline_id)
        with self.assertRaises(DeadlineStateError):
            self.engine.pause(deadline.deadline_id)
        self.engine.complete(deadline.deadline_id)
        self.assertEqual(DeadlineStatus.COMPLETED, self.engine.get(deadline.deadline_id).status)
        with self.assertRaises(DeadlineStateError):
            self.engine.cancel(deadline.deadline_id)
        self.assertEqual(timedelta(0), self.engine.remaining(deadline.deadline_id))

    def test_expired_lists_only_running_overdue(self) -> None:
        first = self.engine.open("CASE-1", DeadlineKind.EVIDENCE_SUPPLEMENT, timedelta(days=3))
        self.engine.open("CASE-1", DeadlineKind.REFUND, timedelta(days=30))
        self.clock.advance(timedelta(days=4))
        expired = self.engine.expired("CASE-1")
        self.assertEqual([first.deadline_id], [d.deadline_id for d in expired])


if __name__ == "__main__":
    unittest.main()
