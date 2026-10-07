# REJECTED.md


## Acceptance criteria refused

### C2: "E7 causes exactly one overdraft fee to be assessed, on Day 2." Refused.
E7 (−620.00, value Day 2) makes **three** days negative once it's booked:
- D2: 250 − 620 = −370 → fee
- D3: −395 + 400 = +5.00 → no fee (survives only by 5.00, *after* the D2 fee)
- D4: 5 − 185 − 180 = −360 → fee (without E7, D4 is +285)
- D5: no movement, −385 → fee

So E7 causes fees on Days 2, 4 and 5. Even if E6 were sent to suspense, D4 = 5 − 185 = −180 and
the count is still three. Test: `test_c2_rejected_e7_causes_three_fees_not_one`.

### C4: "A settlement referencing an unknown authorization must be rejected and the funds must not leave the account." Refused.
A settlement isn't a request; it's a notice that the card scheme has already moved the money
between acquirer and issuer. The issuer can't refuse it. A missing auth happens for real reasons:
offline or stand-in transactions, auths that expired before the merchant presented them, auth
messages lost upstream, or an auth id that doesn't match. Rejecting it would put the bank's money
in a black hole with no customer debit and no case.
**Instead:** post it as `FORCED_SETTLEMENT`, flag `UNMATCHED_SETTLEMENT`, and leave it to
operations to match it or raise a chargeback. The alternative (post to suspense) is in
AMBIGUITIES #18.

### C6: "After E9, all balances and fees return to their pre-E7 values." Refused.
1. **Append-only:** the three fees are never removed. They're offset by three `FEE_REVERSAL`
   entries. The fee history (3 assessed, 3 reversed) is permanently different from "no fees".
2. **Path dependence:** Auth-B was declined *because* of E7 (available −335). Without E7 it would
   have been approved (285 − 90 ≥ 0) and a 90.00 hold would exist. E9 can't undo a decision
   already communicated to a merchant.
3. **What was reported:** Day 5 was reported at −410.00. That report existed and may have
   triggered statements, alerts or limits.
4. Fee reversal is a **policy choice** I made, not an automatic consequence. Without it, Day 6
   is 210.69.

### C7: "The three BHD instalments in E10 must each be BHD 3.334." Refused.
3 × 3.334 = 10.002 ≠ 10.000. That creates 0.002 BHD from nothing. Used 3.333 + 3.333 + 3.334 = 10.000.

### C8: "If the rounded daily accruals do not sum to the capitalized total, the remainder is discarded." Refused.
It contradicts the rule that they must sum exactly. In this design the capitalized total *is* the
sum of the rounded accrual records, so a remainder can't arise. If the records ever disagree with a
fresh recomputation, `_capitalize` raises `InvariantViolation`. Silently discarding money is the one
thing a ledger must never do.

## Criteria accepted (and why they look like traps)

- **C1 (−370.00):** correct. Holds don't touch the ledger balance, and no fee had run yet.
- **C3 (Auth-A accepted):** correct even though Day 2 later restates to −370. Auth decisions use
  what was known at the time.
- **C5 (approved hold affects available balance, not ledger):** true as a property of the model,
  tested directly. In this stream Auth-B is declined, so the condition never happens.

## Approaches abandoned mid-build

<!-- Fill these in from YOUR real build. Examples of the kind of thing to record: -->
- *e.g. Storing a running balance per account. Dropped: back-valued entries made it wrong for past
  days. Balances are now always derived from entries.*
- *e.g. Computing interest once at capitalization from final balances. Dropped: no daily accrual
  records meant nothing to reconcile against and no trail of when an accrual changed.*
- *e.g. Including a day's own fee in its overdraft test. Dropped: a fee could keep itself alive.*
