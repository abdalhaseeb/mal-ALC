# In-Memory Account Ledger Core


An in-memory, append-only account ledger. Python 3.10+ standard library only. No dependencies.

## Run

```bash
python replay.py                        # replays the event stream, prints the per-day report
python -m unittest tests.test_ledger -v # 14 tests cases, all success 
python -m unittest tests.test_known_gap # 1 test, failed as designed 
python -m unittest                      # everything: 15 tests, 1 expected failure
```

## Files

| File | What it is |
|---|---|
| `ledger.py` | The ledger core: entries, holds, fees, interest. All rules live here. |
| `events.py` | The event stream, exactly as given, in the given order. |
| `replay.py` | Feeds events to the ledger, runs end of day, prints the report. |
| `tests/test_ledger.py` | One test per acceptance criterion (accepted and rejected), plus append-only checks. |
| `tests/test_known_gap.py` | The annotated failing test. |

## How to read the output

For each **END OF DAY n**, for each account:

- **closing ledger balance**: all entries with value day ≤ n, *as known at the end of day n*.
- **available balance**: ledger balance minus active holds.
- **earlier days as now known**: past days' closing balances restated. They change when a
  back-valued entry arrives (see Day 5, where Day 2 becomes −395.00).
- **entries booked today**: what was posted today, with its value day.
- **fee assessments**: `FEE` / `FEE_REVERSAL` booked today, and the value day each belongs to.
- **authorization states**: every auth state change today (APPROVED / DECLINED / SETTLED / EXPIRED).
- **errors / exceptions**: events the ledger handled but flagged for operations.

The **FINAL VIEW** at the bottom shows each value day's closing balance after all six days. It also
shows the full accrual trail: every accrual and adjustment, the day it was booked, and that their sum
equals the capitalized interest.

## Key results

| | ACC-001 (AED) | ACC-002 (BHD) |
|---|---|---|
| Day 5 closing as known at end of Day 5 | −410.00 (3 fees: D2, D4, D5) | 0.000 (E10 not yet arrived) |
| Day 6 closing | 285.79 | 10.008 |
| Interest capitalized | 0.79 | 0.008 |
| Auth-A | approved → settled 185.00, 15.00 released | — |
| Auth-B | **declined** (available −335.00) | — |

See `AMBIGUITIES.md` for every judgement call behind these numbers, and `REJECTED.md` for the
criteria refused.
