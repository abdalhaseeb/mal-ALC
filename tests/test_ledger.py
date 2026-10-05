"""Tests for the replay. Each test names the acceptance criterion it covers.
Run: python -m unittest tests.test_ledger -v
"""
import dataclasses
import unittest
from decimal import Decimal as D

from ledger import Ledger
from replay import replay

A, B = "ACC-001", "ACC-002"


class AcceptedCriteria(unittest.TestCase):
    def test_c1_day2_is_minus_370_at_end_of_day5_before_fees(self):
        # Stop right after E8: E7 is booked, Day 5 end-of-day (fee run) has not happened.
        ledger = replay(stop_after="E8")
        self.assertEqual(ledger.balance(A, 2), D("-370.00"))
        self.assertFalse([e for e in ledger.entries if e.kind == "FEE"])

    def test_c3_auth_a_approved_then_settled_for_less(self):
        ledger = replay()
        states = [(r.status, r.amount) for r in ledger.auth_records if r.auth_id == "Auth-A"]
        self.assertEqual(states, [("APPROVED", D("200.00")), ("SETTLED", D("185.00"))])
        settle = [e for e in ledger.entries if e.event_id == "E5"]
        self.assertEqual(settle[0].amount, D("-185.00"))

    def test_c5_auth_b_is_declined_so_no_hold(self):
        ledger = replay()
        b = ledger.latest_auth(A, "Auth-B")
        self.assertEqual(b.status, "DECLINED")
        self.assertEqual(ledger.active_holds(A), [])

    def test_c5_property_an_approved_hold_hits_available_not_ledger(self):
        ledger = Ledger()
        ledger.open_account(A, "AED")
        ledger.credit("X1", A, D("100.00"), 1, 1)
        ledger.authorize("X2", A, "Auth-T", D("90.00"), 1)
        self.assertEqual(ledger.balance(A, 1), D("100.00"))
        self.assertEqual(ledger.available(A, 1), D("10.00"))


class RejectedCriteria(unittest.TestCase):
    """These assert the behaviour we chose INSTEAD of the rejected criteria."""

    def test_c2_rejected_e7_causes_three_fees_not_one(self):
        ledger = replay(stop_after="E8")  # all Day 5 events applied...
        ledger.end_of_day(5)              # ...then the Day 5 fee run, before E9 arrives
        fee_days = [e.value_day for e in ledger.entries if e.kind == "FEE"]
        self.assertEqual(fee_days, [2, 4, 5])
        self.assertEqual(ledger.balance(A, 3), D("5.00"))  # Day 3 survives by 5.00 because of the Day 2 fee

    def test_c4_rejected_unmatched_settlement_is_force_posted_and_flagged(self):
        ledger = replay()
        e6 = [e for e in ledger.entries if e.event_id == "E6"]
        self.assertEqual((e6[0].kind, e6[0].amount), ("FORCED_SETTLEMENT", D("-180.00")))
        self.assertIn("UNMATCHED_SETTLEMENT", [x.code for x in ledger.errors])

    def test_c6_rejected_fees_are_offset_not_removed(self):
        ledger = replay()
        kinds = [e.kind for e in ledger.entries if e.account == A]
        self.assertEqual(kinds.count("FEE"), 3)
        self.assertEqual(kinds.count("FEE_REVERSAL"), 3)
        # Path dependence: without E7, Auth-B would have been approved (285.00 - 90.00 >= 0).
        self.assertEqual(ledger.latest_auth(A, "Auth-B").status, "DECLINED")

    def test_c7_rejected_instalments_sum_exactly(self):
        ledger = replay()
        parts = [e.amount for e in ledger.entries if e.event_id == "E10"]
        self.assertEqual(parts, [D("3.333"), D("3.333"), D("3.334")])
        self.assertEqual(sum(parts), D("10.000"))

    def test_c8_rejected_accruals_equal_capitalized_by_construction(self):
        ledger = replay()
        for acc, expected in ((A, D("0.79")), (B, D("0.008"))):
            total = sum(a.amount for a in ledger.accruals if a.account == acc)
            cap = [e.amount for e in ledger.entries
                   if e.account == acc and e.kind == "INTEREST_CAPITALIZATION"]
            self.assertEqual(total, expected)
            self.assertEqual(cap, [expected])


class FinalNumbers(unittest.TestCase):
    def test_final_closing_balances(self):
        ledger = replay()
        self.assertEqual([ledger.balance(A, d) for d in range(1, 7)],
                         [D("250.00"), D("250.00"), D("650.00"), D("285.00"), D("285.00"), D("285.79")])
        self.assertEqual(ledger.balance(B, 6), D("10.008"))

    def test_day5_as_known_at_end_of_day5(self):
        ledger = replay(stop_after="E8")
        ledger.end_of_day(5)
        self.assertEqual(ledger.balance(A, 5), D("-410.00"))
        self.assertEqual([ledger.balance(A, d) for d in (2, 3, 4)],
                         [D("-395.00"), D("5.00"), D("-385.00")])


class AppendOnly(unittest.TestCase):
    def test_records_are_immutable(self):
        ledger = replay()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ledger.entries[0].amount = D("0")  # type: ignore[misc]

    def test_every_earlier_entry_survives_every_later_event(self):
        from events import EVENTS
        previous = ()
        for ev in EVENTS:
            current = replay(stop_after=ev["id"]).entries
            self.assertEqual(current[:len(previous)], previous)
            previous = current

    def test_double_reversal_is_refused(self):
        ledger = replay()
        ledger.reverse("E9-again", A, "E7", 2, 6)
        self.assertIn("ALREADY_REVERSED", [x.code for x in ledger.errors])


if __name__ == "__main__":
    unittest.main()
