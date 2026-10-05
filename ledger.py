"""In-memory account ledger core.

Design in one paragraph:
- Every money movement is an immutable `Entry` appended to `_entries`. Nothing is
  ever edited or removed; corrections are new entries (REVERSAL, FEE_REVERSAL).
- A balance is never stored. It is always derived: the sum of entries whose
  value_day <= the day asked about. This is what makes back-valued entries work.
- Authorization state is also append-only: each change is a new `AuthRecord`;
  the current state of an auth is its latest record.
- Interest accruals are append-only `Accrual` records. If a back-valued entry
  changes a past day's balance, we append an adjustment rather than edit.
- `end_of_day(day)` re-evaluates fees and accruals for every day up to `day`,
  because a back-valued entry can change any earlier day.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

# ---------------------------------------------------------------------------
# Constants. Every one of these is explained in NUMBERS.md.
# ---------------------------------------------------------------------------
PRECISION = {"AED": Decimal("0.01"), "BHD": Decimal("0.001")}
ROUNDING = ROUND_HALF_UP
OVERDRAFT_FEE = Decimal("25.00")
OVERDRAFT_FEE_CCY = "AED"
DAILY_INTEREST_RATE = Decimal("0.0004")  # 0.04% per day
WINDOW_LAST_DAY = 6                       # interest capitalizes at end of this day
HOLD_EXPIRY_DAYS = 7                      # approved hold auto-expires after this many days

ZERO = Decimal("0")


def rnd(amount: Decimal, ccy: str) -> Decimal:
    """Round to the currency's own precision."""
    return amount.quantize(PRECISION[ccy], rounding=ROUNDING)


class InvariantViolation(Exception):
    """Raised when the ledger detects an internal inconsistency. Never swallowed."""


# ---------------------------------------------------------------------------
# Immutable records (frozen=True: any attempt to mutate raises)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Entry:
    seq: int
    event_id: str
    account: str
    kind: str          # CREDIT, DEBIT, SETTLEMENT, FORCED_SETTLEMENT, REVERSAL,
                       # FEE, FEE_REVERSAL, INTEREST_CAPITALIZATION
    amount: Decimal    # signed: + credit, - debit
    value_day: int
    booked_day: int
    ref: str = ""      # auth id, reversed event id, "D<n>" for fees, instalment "i/n"


@dataclass(frozen=True)
class AuthRecord:
    seq: int
    event_id: str
    account: str
    auth_id: str
    status: str        # APPROVED, DECLINED, SETTLED, EXPIRED
    amount: Decimal    # hold amount (APPROVED/DECLINED/EXPIRED) or settled amount (SETTLED)
    day: int
    detail: str = ""


@dataclass(frozen=True)
class Accrual:
    seq: int
    account: str
    for_day: int       # the value day whose closing balance this accrual is for
    amount: Decimal    # first accrual, or a +/- adjustment after a back-valued change
    booked_day: int


@dataclass(frozen=True)
class ErrorRecord:
    seq: int
    day: int
    event_id: str
    account: str
    code: str
    detail: str


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------
class Ledger:
    def __init__(self) -> None:
        self._accounts: dict[str, str] = {}
        self._entries: list[Entry] = []
        self._auths: list[AuthRecord] = []
        self._accruals: list[Accrual] = []
        self._errors: list[ErrorRecord] = []
        self._seq = 0

    # ---- read-only views (tuples, so callers cannot append or remove) -------
    @property
    def entries(self) -> tuple[Entry, ...]:
        return tuple(self._entries)

    @property
    def auth_records(self) -> tuple[AuthRecord, ...]:
        return tuple(self._auths)

    @property
    def accruals(self) -> tuple[Accrual, ...]:
        return tuple(self._accruals)

    @property
    def errors(self) -> tuple[ErrorRecord, ...]:
        return tuple(self._errors)

    def accounts(self) -> dict[str, str]:
        return dict(self._accounts)

    def ccy(self, account: str) -> str:
        return self._accounts[account]

    # ---- internals ----------------------------------------------------------
    def _next(self) -> int:
        self._seq += 1
        return self._seq

    def _post(self, event_id, account, kind, amount, value_day, booked_day, ref="") -> Entry:
        ccy = self._accounts[account]
        if amount != rnd(amount, ccy):
            raise InvariantViolation(f"{event_id}: {amount} not at {ccy} precision")
        e = Entry(self._next(), event_id, account, kind, amount, value_day, booked_day, ref)
        self._entries.append(e)
        return e

    def _error(self, day, event_id, account, code, detail) -> None:
        self._errors.append(ErrorRecord(self._next(), day, event_id, account, code, detail))

    # ---- setup --------------------------------------------------------------
    def open_account(self, account: str, ccy: str) -> None:
        if ccy not in PRECISION:
            raise ValueError(f"unsupported currency {ccy}")
        self._accounts[account] = ccy  # opening balance is 0 for both accounts

    # ---- derived balances ---------------------------------------------------
    def balance(self, account: str, value_day: int) -> Decimal:
        """Closing ledger balance for `value_day`, given everything booked so far."""
        total = sum((e.amount for e in self._entries
                     if e.account == account and e.value_day <= value_day), ZERO)
        return rnd(total, self._accounts[account])

    def latest_auth(self, account: str, auth_id: str) -> AuthRecord | None:
        recs = [r for r in self._auths if r.account == account and r.auth_id == auth_id]
        return recs[-1] if recs else None

    def active_holds(self, account: str) -> list[AuthRecord]:
        latest: dict[str, AuthRecord] = {}
        for r in self._auths:
            if r.account == account:
                latest[r.auth_id] = r
        return [r for r in latest.values() if r.status == "APPROVED"]

    def available(self, account: str, day: int) -> Decimal:
        return self.balance(account, day) - sum((h.amount for h in self.active_holds(account)), ZERO)

    # ---- events -------------------------------------------------------------
    def credit(self, event_id, account, amount, value_day, booked_day) -> None:
        self._post(event_id, account, "CREDIT", amount, value_day, booked_day)

    def debit(self, event_id, account, amount, value_day, booked_day) -> None:
        self._post(event_id, account, "DEBIT", -amount, value_day, booked_day)

    def credit_instalments(self, event_id, account, total, n, value_day, booked_day) -> None:
        """Split `total` into n parts at currency precision. The first n-1 parts are
        rounded DOWN; the last part takes the remainder so the parts sum exactly."""
        unit = PRECISION[self._accounts[account]]
        base = (total / n).quantize(unit, rounding=ROUND_DOWN)
        parts = [base] * (n - 1) + [total - base * (n - 1)]
        if sum(parts) != total:
            raise InvariantViolation(f"{event_id}: instalments {parts} != {total}")
        for i, p in enumerate(parts, start=1):
            self._post(event_id, account, "CREDIT", p, value_day, booked_day, ref=f"{i}/{n}")

    def authorize(self, event_id, account, auth_id, amount, day) -> str:
        """Approve only if available balance stays >= 0 after the hold.
        Uses what is known *now*; the decision is never revisited later."""
        avail = self.available(account, day)
        after = avail - amount
        status = "APPROVED" if after >= 0 else "DECLINED"
        self._auths.append(AuthRecord(self._next(), event_id, account, auth_id, status, amount, day,
                                      f"available {avail} -> {after} if held"))
        return status

    def settle(self, event_id, account, auth_id, amount, value_day, booked_day) -> None:
        rec = self.latest_auth(account, auth_id)
        if rec is None or rec.status != "APPROVED":
            # Scheme settlement has already moved the money; the issuer cannot refuse it.
            # Post it to the customer as a forced settlement and raise an exception for ops.
            code = "UNMATCHED_SETTLEMENT" if rec is None else f"SETTLEMENT_ON_{rec.status}_AUTH"
            self._error(booked_day, event_id, account, code,
                        f"{auth_id} settles {amount}; no active hold. Force-posted, flagged for review/chargeback")
            self._post(event_id, account, "FORCED_SETTLEMENT", -amount, value_day, booked_day, ref=auth_id)
            return
        if amount > rec.amount:
            self._error(booked_day, event_id, account, "OVER_SETTLEMENT",
                        f"{auth_id} hold {rec.amount}, settled {amount}. Posted, flagged")
        self._post(event_id, account, "SETTLEMENT", -amount, value_day, booked_day, ref=auth_id)
        released = rec.amount - amount
        self._auths.append(AuthRecord(self._next(), event_id, account, auth_id, "SETTLED", amount,
                                      booked_day, f"hold {rec.amount} released; residual {released}"))

    def reverse(self, event_id, account, target_event_id, value_day, booked_day) -> None:
        originals = [e for e in self._entries
                     if e.event_id == target_event_id and e.account == account
                     and e.kind in ("CREDIT", "DEBIT", "SETTLEMENT", "FORCED_SETTLEMENT")]
        if not originals:
            self._error(booked_day, event_id, account, "REVERSAL_TARGET_NOT_FOUND", target_event_id)
            return
        if any(e.kind == "REVERSAL" and e.ref == target_event_id for e in self._entries):
            self._error(booked_day, event_id, account, "ALREADY_REVERSED", target_event_id)
            return
        for o in originals:
            self._post(event_id, account, "REVERSAL", -o.amount, value_day, booked_day, ref=target_event_id)

    # ---- end of day ---------------------------------------------------------
    def end_of_day(self, day: int) -> None:
        for account in self._accounts:
            self._expire_holds(account, day)
            self._assess_fees(account, day)
            self._accrue_interest(account, day)
            if day == WINDOW_LAST_DAY:
                self._capitalize(account, day)

    def _expire_holds(self, account, day) -> None:
        for h in self.active_holds(account):
            if day - h.day >= HOLD_EXPIRY_DAYS:
                self._auths.append(AuthRecord(self._next(), "EOD", account, h.auth_id, "EXPIRED",
                                              h.amount, day, f"no settlement within {HOLD_EXPIRY_DAYS} days"))

    def net_fee(self, account: str, fee_day: int) -> Decimal:
        total = sum((e.amount for e in self._entries
                     if e.account == account and e.kind in ("FEE", "FEE_REVERSAL")
                     and e.ref == f"D{fee_day}"), ZERO)
        return rnd(total, self._accounts[account])

    def _assess_fees(self, account, day) -> None:
        """Re-check every day 1..day in ascending order (an earlier fee affects later days).
        A day is overdrawn if its closing balance EXCLUDING its own fee is negative;
        otherwise a fee would keep itself alive after the cause was reversed."""
        for d in range(1, day + 1):
            own = self.net_fee(account, d)
            basis = self.balance(account, d) - own
            if basis < 0 and own == 0:
                if self._accounts[account] != OVERDRAFT_FEE_CCY:
                    self._error(day, "EOD", account, "FEE_CCY_MISMATCH",
                                f"D{d} overdrawn; fee is in {OVERDRAFT_FEE_CCY}, no FX in scope")
                    continue
                self._post("EOD", account, "FEE", -OVERDRAFT_FEE, d, day, ref=f"D{d}")
            elif basis >= 0 and own != 0:
                self._post("EOD", account, "FEE_REVERSAL", -own, d, day, ref=f"D{d}")

    def accrued_for_day(self, account: str, d: int) -> Decimal:
        total = sum((a.amount for a in self._accruals if a.account == account and a.for_day == d), ZERO)
        return rnd(total, self._accounts[account])

    def target_accrual(self, account: str, d: int) -> Decimal:
        bal = self.balance(account, d)
        return rnd(bal * DAILY_INTEREST_RATE if bal > 0 else ZERO, self._accounts[account])

    def _accrue_interest(self, account, day) -> None:
        for d in range(1, day + 1):
            delta = self.target_accrual(account, d) - self.accrued_for_day(account, d)
            if delta != 0:
                self._accruals.append(Accrual(self._next(), account, d, delta, day))

    def _capitalize(self, account, day) -> None:
        total = sum((a.amount for a in self._accruals if a.account == account), ZERO)
        recomputed = sum((self.target_accrual(account, d) for d in range(1, WINDOW_LAST_DAY + 1)), ZERO)
        if total != recomputed:
            raise InvariantViolation(f"{account}: accrual records {total} != recomputed {recomputed}")
        if total > 0:
            self._post("EOD", account, "INTEREST_CAPITALIZATION", total, WINDOW_LAST_DAY, day,
                       ref=f"D1-D{WINDOW_LAST_DAY}")
