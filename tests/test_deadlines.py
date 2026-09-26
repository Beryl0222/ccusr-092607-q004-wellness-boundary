import sys
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from support import T0
from wellness_boundary.clock import ManualClock
from wellness_boundary.deadlines import DeadlineEngine, DeadlineKind, DeadlineStatus


class DeadlineEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = ManualClock(T0)
        self.engine = DeadlineEngine(self.clock)

    def test_remaining_counts_down_with_clock(self) -> None:
        self.engine.start("case-1", DeadlineKind.COOLING_OFF, timedelta(days=7))
        self.clock.advance(timedelta(days=2))
        self.assertEqual(timedelta(days=5), self.engine.remaining("case-1", DeadlineKind.COOLING_OFF))
        self.assertEqual(DeadlineStatus.RUNNING, self.engine.status("case-1", DeadlineKind.COOLING_OFF))

    def test_pause_freezes_and_resume_continues_original_countdown(self) -> None:
        self.engine.start("case-1", DeadlineKind.REFUND, timedelta(days=7))
        self.clock.advance(timedelta(days=4))
        self.engine.pause("case-1", DeadlineKind.REFUND)
        self.assertEqual(DeadlineStatus.PAUSED, self.engine.status("case-1", DeadlineKind.REFUND))
        self.clock.advance(timedelta(days=30))  # 服务暂停期间不计时
        self.assertEqual(timedelta(days=3), self.engine.remaining("case-1", DeadlineKind.REFUND))
        self.engine.resume("case-1", DeadlineKind.REFUND)
        # 恢复后继续原有倒计时：剩余仍是 3 天，而不是重新算 7 天
        self.assertEqual(timedelta(days=3), self.engine.remaining("case-1", DeadlineKind.REFUND))
        self.clock.advance(timedelta(days=3))
        self.assertTrue(self.engine.is_expired("case-1", DeadlineKind.REFUND))

    def test_expiry_only_after_duration_elapsed(self) -> None:
        self.engine.start("case-1", DeadlineKind.RECTIFICATION, timedelta(days=15))
        self.clock.advance(timedelta(days=15, seconds=-1))
        self.assertFalse(self.engine.is_expired("case-1", DeadlineKind.RECTIFICATION))
        self.clock.advance(timedelta(seconds=1))
        self.assertTrue(self.engine.is_expired("case-1", DeadlineKind.RECTIFICATION))

    def test_complete_stops_deadline(self) -> None:
        self.engine.start("case-1", DeadlineKind.EVIDENCE_SUPPLEMENT, timedelta(days=10))
        self.engine.complete("case-1", DeadlineKind.EVIDENCE_SUPPLEMENT)
        self.clock.advance(timedelta(days=30))
        self.assertEqual(DeadlineStatus.COMPLETED, self.engine.status("case-1", DeadlineKind.EVIDENCE_SUPPLEMENT))
        self.assertFalse(self.engine.is_expired("case-1", DeadlineKind.EVIDENCE_SUPPLEMENT))

    def test_invalid_transitions_are_rejected(self) -> None:
        self.engine.start("case-1", DeadlineKind.REFUND, timedelta(days=7))
        with self.assertRaises(ValueError):
            self.engine.start("case-1", DeadlineKind.REFUND, timedelta(days=7))
        with self.assertRaises(ValueError):
            self.engine.resume("case-1", DeadlineKind.REFUND)
        self.engine.pause("case-1", DeadlineKind.REFUND)
        with self.assertRaises(ValueError):
            self.engine.pause("case-1", DeadlineKind.REFUND)
        with self.assertRaises(KeyError):
            self.engine.remaining("case-1", DeadlineKind.COOLING_OFF)


if __name__ == "__main__":
    unittest.main()
