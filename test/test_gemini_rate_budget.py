"""Unit tests for shared FIFO Gemini rate budget."""
import threading
import time
import unittest

from services.gemini_rate_budget import GeminiRateBudget, reset_shared_gemini_budget_for_tests


class GeminiRateBudgetTest(unittest.TestCase):
    def setUp(self):
        self.budget = GeminiRateBudget(
            max_requests_per_minute=3,
            usable_tpm_headroom=10_000,
            persist_to_db=False,
        )

    def test_shared_counters_across_record(self):
        self.assertTrue(self.budget.record(100))
        self.assertTrue(self.budget.record(100))
        self.assertEqual(self.budget.requests_this_minute, 2)
        status = self.budget.status()
        self.assertEqual(status["remaining_requests"], 1)

    def test_admit_wait_false_fails_when_exhausted(self):
        for _ in range(3):
            self.assertTrue(self.budget.admit(1, wait=False))
        self.assertFalse(self.budget.admit(1, wait=False))

    def test_two_clients_share_rpm(self):
        a = self.budget
        b = self.budget  # same instance = shared
        self.assertTrue(a.admit(1, wait=False))
        self.assertTrue(b.admit(1, wait=False))
        self.assertTrue(a.admit(1, wait=False))
        self.assertFalse(b.admit(1, wait=False))
        self.assertEqual(a.requests_this_minute, 3)

    def test_fifo_order_under_contention(self):
        """Head-of-queue is admitted before later waiters when capacity frees."""
        budget = GeminiRateBudget(
            max_requests_per_minute=1,
            usable_tpm_headroom=10_000,
            persist_to_db=False,
        )
        self.assertTrue(budget.admit(1, wait=False))

        order = []
        errors = []

        def waiter(name):
            try:
                ok = budget.admit(1, wait=True, max_waits=5)
                if ok:
                    order.append(name)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=waiter, args=("first",))
        t2 = threading.Thread(target=waiter, args=("second",))
        t1.start()
        time.sleep(0.1)  # first should be queued as head
        t2.start()
        time.sleep(0.1)

        def _free_window():
            with budget._cond:
                budget.minute_start_time = time.time() - 61
                budget.requests_this_minute = 0
                budget.tokens_this_minute = 0
                budget._cond.notify_all()

        # One free slot → head ("first") admits; then free again for "second"
        _free_window()
        time.sleep(0.3)
        _free_window()
        t1.join(timeout=15)
        t2.join(timeout=15)
        self.assertFalse(errors, errors)
        self.assertEqual(order, ["first", "second"])

    def test_reset_shared_singleton(self):
        b1 = reset_shared_gemini_budget_for_tests()
        b1.persist_to_db = False
        b1.admit(1, wait=False)
        b2 = reset_shared_gemini_budget_for_tests()
        b2.persist_to_db = False
        self.assertEqual(b2.requests_this_minute, 0)
        self.assertIsNot(b1, b2)


class SharedAnalyzerBudgetTest(unittest.TestCase):
    def test_two_analyzers_same_budget(self):
        from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
        from services.gemini_rate_budget import GeminiRateBudget

        budget = GeminiRateBudget(
            max_requests_per_minute=2, persist_to_db=False
        )
        a1 = EnhancedAIAnalyzer.__new__(EnhancedAIAnalyzer)
        a1._budget = budget
        a1.max_requests_per_minute = 2
        a1.usable_tpm_headroom = budget.usable_tpm_headroom
        a2 = EnhancedAIAnalyzer.__new__(EnhancedAIAnalyzer)
        a2._budget = budget
        a2.max_requests_per_minute = 2
        a2.usable_tpm_headroom = budget.usable_tpm_headroom

        self.assertTrue(budget.admit(1, wait=False))
        self.assertEqual(a1.requests_this_minute, 1)
        self.assertEqual(a2.requests_this_minute, 1)
        self.assertTrue(budget.admit(1, wait=False))
        self.assertFalse(budget.admit(1, wait=False))


if __name__ == "__main__":
    unittest.main()
