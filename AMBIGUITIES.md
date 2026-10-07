# AMBIGUITIES.md



Each entry: **the ambiguity** → **what I decided** → *what would change otherwise*.

## Time and ordering

1. **E10 is labelled Day 5 but listed after E9 (Day 6).** The stream says "replayed in this order".
   → Replayed in the given order. E10 arrives after Day 5 has closed, so it's processed on Day 6
   with value day 5 kept, and logged as `LATE_EVENT`.
   *If sorted by booked day instead: the Day 5 report would show ACC-002 at 10.000 rather than
   0.000. Final numbers are identical (10.008 and 0.008 interest).*
2. **What "Day" means.** → An abstract processing day with one end-of-day run. No calendar,
   time zone, cut-off time or business-day rules.
3. **What the per-day closing balance shows.** As known that day, or restated after later
   back-valued entries? → The report prints both: today's figure plus "earlier days as now known",
   and a final restated table.

## Fees

4. **Are past days' fees reassessed when a back-valued entry arrives?** → Yes. Every end of day
   re-checks every earlier day. This is what produces 3 fees at end of Day 5.
5. **Are fees reversed when the cause disappears (E9)?** The spec only says when to assess.
   → Yes, by appending a `FEE_REVERSAL`. A fee caused by a posting that was later reversed is
   the bank's error, not the customer's.
   *If not reversed: Day 6 closes at 210.69 rather than 285.79.*
6. **Does a day's own fee count in its overdraft test?** → No (see NUMBERS.md). Otherwise a
   fee can keep itself alive.
7. **Do earlier fees count towards later days?** → Yes, they're real entries. That's why Day 3 is
   +5.00 rather than +30.00 and so escapes a fee.
8. **Fee on the BHD account.** The fee is in AED; there's no FX rate. → An overdrawn BHD account
   would log `FEE_CCY_MISMATCH` instead of guessing a rate. Never triggered.
9. **Fee value date for a past day.** → Value date = the day assessed (per the rule); booked
   date = the end of day when it was detected. They differ (fee for D2 booked on D5).

## Interest

10. **Which balance earns interest, as known that day or restated?** → Restated. Accruals are
    append-only records; when a back-valued entry changes a past day, an adjustment is appended
    (D2: +0.10 on D2, −0.10 on D5, +0.10 on D6).
11. **Does interest accrue on Day 6, and before or after capitalization?** → Day 6 accrues on
    285.00, then the total is capitalized with value day 6. Capitalization doesn't earn interest
    inside the window.
12. **Rounding per day versus on the total.** → Per day (the rule says daily accruals are
    rounded). This loses 0.012 relative to the unrounded 0.802. The capitalized total is defined
    as the sum of the rounded accruals, so there is no remainder.
13. **Do fees reduce the interest basis?** → Yes; fees are ledger entries like any other.

## Authorizations and settlements

14. **"Ledger balance" in the auth check: today's balance, or the balance at the auth's value
    date?** → Entries booked so far with value day ≤ today. Holds are subtracted.
15. **Is an auth re-decided when a later back-valued entry changes history?** → No. Approval is
    a commitment made with what was known then. Auth-A stays approved even though Day 2 later
    restates to −370.
16. **Settling for less than the hold (Auth-A 185 vs 200).** → Accepted; the remaining 15.00 is
    released.
17. **Settling for more than the hold.** → Posted and flagged `OVER_SETTLEMENT`. No tolerance.
18. **Settlement with no auth (Auth-Z).** → Force-posted to the customer and flagged
    `UNMATCHED_SETTLEMENT`. *Alternative: post to a suspense account; Day 4 onward would be
    180.00 higher.* See REJECTED.md.
19. **Auth-B never settles.** It's declined anyway. Had it been approved, the hold would
    stay active until `HOLD_EXPIRY_DAYS` (7), which is beyond the window.
20. **Can available balance be negative?** → Yes (−410.00 on Day 5). The rule blocks *new holds*;
    it doesn't stop settlements, fees or back-valued debits.

## Reversals and instalments

21. **Reversal value date.** E9 has value day 2, the same as E7, so it cancels E7 in every
    restated day. → As given.
22. **Reversing a reversal / reversing twice.** → Refused, logged `ALREADY_REVERSED`.
23. **Which instalment takes the extra 0.001.** → The last one (3.333, 3.333, 3.334).
24. **Instalments: one event or three?** → One event id (E10) with three entries referenced 1/3,
    2/3, 3/3. They're reversed together if E10 is ever reversed.
