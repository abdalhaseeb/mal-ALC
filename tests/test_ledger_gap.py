"""THE DELIBERATELY FAILING TEST.

Run: python -m unittest tests.test_known_gap -v      (expected: 1 failure)
"""
import unittest
from decimal import Decimal as D

from events import EVENTS
from replay import replay


class KnownGap(unittest.TestCase):
    def test_redelivered_event_is_applied_once(self):
        # Simulate an upstream retry: E4 (credit 400.00) is delivered twice.
        # In production this happens all the time: a network timeout, the sender
        # never gets an ack, and it resends the same message.
        stream = list(EVENTS)
        e4 = next(e for e in stream if e["id"] == "E4")
        stream.insert(stream.index(e4) + 1, dict(e4))

        ledger = replay(stream, stop_after="E5")  # stops at the first E5; Day 3 has closed

        # EXPECTED: Day 3 closes at 650.00, the same as with a single delivery.
        # ACTUAL:   1050.00. The ledger credits 400.00 a second time.
        #
        # WHAT IT REVEALS: the ledger trusts the caller to deliver each event exactly
        # once. Entries carry event_id, but nothing checks whether an event_id has
        # already been applied. Only reversals are guarded (ALREADY_REVERSED), and
        # only because a reversal has a target to look up. Plain credits, debits,
        # authorizations and settlements have no such guard.
        #
        # WHY IT IS NOT FIXED: the fix is small (refuse an event_id already seen and
        # log DUPLICATE_EVENT), but deciding what counts as "the same event" is not
        # (same id but different amount? a replay after a restart?). In production
        # this is an idempotency-key store with a retention window, which ties into
        # the unbounded-state question in the architecture document.
        self.assertEqual(ledger.balance("ACC-001", 3), D("650.00"))


if __name__ == "__main__":
    unittest.main()
