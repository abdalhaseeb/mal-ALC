# NUMBERS.md


## Given by the spec (not my choice, listed for completeness)

| Constant | Value | Note |
|---|---|---|
| Overdraft fee | AED 25.00 | Once per day per account |
| Daily interest | 0.04% = 0.0004 | Positive closing balances only |
| AED / BHD precision | 2 / 3 decimals | ISO 4217 minor units |
| Window | Day 1–6 | Capitalize at end of Day 6 |

## Chosen by me

| Constant | Value | Why this value, and not half of it |
|---|---|---|
| `ROUNDING` | ROUND_HALF_UP | The rounding customers and auditors expect on a statement. Half-even (banker's rounding) removes bias over millions of rows but is harder to explain to a customer. No value in this data falls on a .5 boundary, so the choice changes no number here. "Half" doesn't apply to a mode; the alternative is half-even. |
| `HOLD_EXPIRY_DAYS` | 7 | Matches the typical card-scheme window for a normal retail authorization. Half (3.5 → 3 days) would release holds before many merchants present their batch, so customers could spend money that's already committed, which leads to forced posts and overdrafts. Longer windows (up to 30 days) belong to specific merchant types (hotels, car rental) and would need a per-category table. Not triggered in this window. |
| Instalment split | first n−1 rounded **down**, last takes the remainder | Rounding each part *up* overshoots (3 × 3.334 = 10.002). Rounding down then putting the remainder on the last part always sums exactly. The remainder can be at most (n−1) minor units, so it's bounded. |
| Fee look-back | unbounded (every day since Day 1) | With a 6-day window, re-checking every day costs nothing and is always correct. Half of "unbounded" isn't meaningful; the real production choice is a back-value cutoff (for example, 30 days or the accounting period), covered in the architecture document. |
| Fee test | balance **excluding that day's own fee** < 0 | Including its own fee would keep a fee alive after its cause was reversed: Day 2 after E9 would be 250 − 25 = 225 ≥ 0, which happens to work here, but a day sitting between 0 and 25 would never get its fee reversed. |
| Over-settlement | no tolerance; post it and flag it | Any number I picked (10%, 15%, 20%) depends on the merchant category (tips, fuel). I chose to flag rather than invent a figure. |

## Derived numbers you must be able to reproduce by hand

- Day 2 at end of Day 5, before fees: 1200 − 950 − 620 = **−370.00**
- After fees cascade: D2 −395, D3 −395 + 400 = **5.00**, D4 5 − 185 − 180 − 25 = **−385**, D5 **−410**
- Auth-B: available at Day 5 = −335.00 (Day 5 ledger before fees), −335 − 90 = −425 → **declined**
- Interest: 250 × 0.0004 = 0.10; 650 → 0.26; 285 → 0.114 → 0.11 (×3) → **0.79**. Unrounded 0.802.
- BHD: 10.000 × 0.0004 = 0.004 × 2 days = **0.008**
