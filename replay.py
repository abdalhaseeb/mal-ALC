"""Replay the event stream through the ledger and print a per-day report.

Run:  python replay.py

Day boundaries: when an event arrives with a later booked day than the current
processing day, end-of-day runs for every day in between. The stream is replayed
in the GIVEN order. E10 says Day 5 but arrives after E9 (Day 6), i.e. after Day 5
has closed. It is processed on Day 6 with its value day 5 preserved, and logged as
LATE_EVENT. (See AMBIGUITIES.md.)
"""
from __future__ import annotations

from events import ACCOUNTS, EVENTS
from ledger import Ledger, WINDOW_LAST_DAY



def apply(ledger: Ledger, ev: dict, day: int) -> None:
    t, acc = ev["type"], ev["account"]
    if t == "CREDIT":
        ledger.credit(ev["id"], acc, ev["amount"], ev["value_day"], day)
    elif t == "DEBIT":
        ledger.debit(ev["id"], acc, ev["amount"], ev["value_day"], day)
    elif t == "CREDIT_INSTALMENTS":
        ledger.credit_instalments(ev["id"], acc, ev["amount"], ev["instalments"], ev["value_day"], day)
    elif t == "AUTHORIZATION":
        ledger.authorize(ev["id"], acc, ev["auth_id"], ev["amount"], day)
    elif t == "SETTLEMENT":
        ledger.settle(ev["id"], acc, ev["auth_id"], ev["amount"], ev["value_day"], day)
    elif t == "REVERSAL":
        ledger.reverse(ev["id"], acc, ev["target"], ev["value_day"], day)
    else:
        raise ValueError(f"unknown event type {t}")


def replay(events=EVENTS, stop_after: str | None = None, on_eod=None) -> Ledger:
    """Replay `events`. If `stop_after` is an event id, stop right after applying it
    (no further end-of-day runs). `on_eod(ledger, day)` is called after each EOD."""
    ledger = Ledger()
    for acc, ccy in ACCOUNTS:
        ledger.open_account(acc, ccy)

    current = 1
    for ev in events:
        if ev["day"] > current:
            for d in range(current, ev["day"]):
                ledger.end_of_day(d)
                if on_eod:
                    on_eod(ledger, d)
            current = ev["day"]
        if ev["day"] < current:
            ledger._error(current, ev["id"], ev["account"], "LATE_EVENT",
                          f"labelled Day {ev['day']}, arrived after Day {current - 1} closed; "
                          f"processed on Day {current}, value day {ev['value_day']} kept")
        apply(ledger, ev, current)
        if ev["id"] == stop_after:
            return ledger

    for d in range(current, WINDOW_LAST_DAY + 1):
        ledger.end_of_day(d)
        if on_eod:
            on_eod(ledger, d)
    return ledger


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def print_day(ledger: Ledger, day: int) -> None:
    print(f"\n{'=' * 72}\nEND OF DAY {day}\n{'=' * 72}")
    for acc, ccy in ledger.accounts().items():
        holds = ledger.active_holds(acc)
        print(f"\n{acc} ({ccy})")
        print(f"  closing ledger balance (value day {day}): {ledger.balance(acc, day)}")
        print(f"  available balance: {ledger.available(acc, day)}"
              f"  (active holds: {', '.join(f'{h.auth_id} {h.amount}' for h in holds) or 'none'})")

        if day > 1:
            restated = ", ".join(f"D{d} {ledger.balance(acc, d)}" for d in range(1, day))
            print(f"  earlier days as now known: {restated}")

        booked = [e for e in ledger.entries
                  if e.account == acc and e.booked_day == day and e.kind not in ("FEE", "FEE_REVERSAL")]
        print("  entries booked today:")
        for e in booked or []:
            ref = f" ref={e.ref}" if e.ref else ""
            print(f"    {e.event_id:<4} {e.kind:<24} {e.amount:>+10} value day {e.value_day}{ref}")
        if not booked:
            print("    none")

        fees = [e for e in ledger.entries
                if e.account == acc and e.booked_day == day and e.kind in ("FEE", "FEE_REVERSAL")]
        print("  fee assessments:")
        for e in fees:
            print(f"    {e.kind:<13} {e.amount:>+8} for value day {e.value_day}")
        if not fees:
            print("    none")

        auths = [a for a in ledger.auth_records if a.account == acc and a.day == day]
        print("  authorization states:")
        for a in auths:
            print(f"    {a.auth_id}: {a.status} {a.amount} ({a.detail}) [{a.event_id}]")
        if not auths:
            print("    no changes")

        errs = [x for x in ledger.errors if x.account == acc and x.day == day]
        print("  errors / exceptions:")
        for x in errs:
            print(f"    {x.code} [{x.event_id}]: {x.detail}")
        if not errs:
            print("    none")


def print_summary(ledger: Ledger) -> None:
    print(f"\n{'=' * 72}\nFINAL VIEW (all entries booked by end of Day {WINDOW_LAST_DAY})\n{'=' * 72}")
    for acc, ccy in ledger.accounts().items():
        print(f"\n{acc} ({ccy})")
        print(f"  {'day':<5}{'closing':>12}{'net fee':>10}{'accrual':>10}   accrual records (booked day: amount)")
        for d in range(1, WINDOW_LAST_DAY + 1):
            recs = [a for a in ledger.accruals if a.account == acc and a.for_day == d]
            trail = ", ".join(f"D{a.booked_day}: {a.amount:+}" for a in recs) or "-"
            print(f"  D{d:<4}{ledger.balance(acc, d):>12}{ledger.net_fee(acc, d):>10}"
                  f"{ledger.accrued_for_day(acc, d):>10}   {trail}")
        cap = [e for e in ledger.entries if e.account == acc and e.kind == "INTEREST_CAPITALIZATION"]
        total = sum((a.amount for a in ledger.accruals if a.account == acc), 0)
        print(f"  sum of rounded daily accruals: {total}")
        print(f"  capitalized: {cap[0].amount if cap else '0'} (value day {WINDOW_LAST_DAY})")
    print(f"\nentries in ledger: {len(ledger.entries)} (append-only; none edited or removed)")


if __name__ == "__main__":
    ledger = replay(on_eod=print_day)
    print_summary(ledger)
