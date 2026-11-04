# NUMBERS

Every numeric constant in the code, why it has the value it has, and the
"why not half it" sanity check — i.e. what would go wrong, or what would be
detected, if the value were 2× off. Constants fixed by the brief are marked
*given*; the check for those is whether the magnitude is plausible, because a
spec can be wrong too.

| Constant | Value | Where |
|---|---|---|
| `PRECISION["AED"]` | 2 | `money.py` |
| `PRECISION["BHD"]` | 3 | `money.py` |
| `ROUNDING` | ROUND_HALF_UP | `money.py` |
| `OVERDRAFT_FEE["AED"]` | 25.00 | `engine.py` |
| `DAILY_INTEREST_RATE` | 0.0004 | `engine.py` |
| `WINDOW_DAYS` | 6 | `scenario.py` |
| day index base | 1 | throughout |
| overdraft threshold | `< 0` | `engine.py` |
| interest threshold | `> 0` | `engine.py` |
| instalment count (E10) | 3 | `scenario.py` |
| instalment remainder position | last | `money.py` |
| `seq` start | 1 | `ledger.py` |
| capitalisation day | `WINDOW_DAYS` | `engine.py` |

---

### `PRECISION["AED"] = 2`, `PRECISION["BHD"] = 3` — *given*

ISO 4217 minor units: the dirham has 100 fils, the Bahraini dinar 1,000 fils.
The spec states both, and they match the standard, so there is nothing to
choose. The table is a hard lookup — an unlisted currency raises
`UnknownCurrency` instead of defaulting to 2 — because a silent 2dp default
on a 3dp currency loses one digit on every posting and nothing would ever
flag it.

**Half it:** AED at 1dp would coarsen every accrual (0.10 → 0.1, 0.25 →
0.3, 0.17 → 0.2) and the 0.93 total would drift to 1.1 — survivable but
wrong. BHD at 1dp is worse: 3.333 becomes unrepresentable and the 0.004 daily
accrual rounds to 0.0, so the account earns nothing. Doubling is subtler: AED at 4dp would make 0.166 "exact", the accruals would sum to
0.9180 instead of 0.93, and the ledger would carry sub-fils amounts no bank
can pay out. The precision table is the one place where "more" is as wrong as
"less".

### `ROUNDING = ROUND_HALF_UP`

Not specified. Half-up is commercial rounding and what a customer expects on
a statement. The alternative, ROUND_HALF_EVEN (banker's), minimises bias over
many operations and is common in accumulators. In this window no exact .5
tie occurs at the rounding digit, so the choice changes nothing — which is
exactly why it has to be written down: it is a latent behaviour. Documented
in `tests/test_money.py` (`test_quantize_is_half_up`).

**"Half it"** does not apply to a mode; the equivalent check is: would a
different mode be detected? Not by this scenario. It would be by a test with
a tie, which is why that test exists.

### `OVERDRAFT_FEE["AED"] = 25.00` — *given*

Plausibility: AED 25 is in the range of real UAE bank overdraft/returned-item
charges (tens of dirhams), so the magnitude is credible.

**Half it (12.50):** the cascade on this stream would cost the customer 37.50
instead of 75.00 and Day 3 would restate to 17.50 rather than 5.00 — still
positive, so the *count* of fees (three) is unchanged. **Double it (50.00):**
Day 3 would restate to −20.00 and pick up a fourth fee (→ −70.00), and Day 4/5
would close at −305.00 / −355.00. So the fee size is a lever on how far a single backdated debit
cascades. At 25.00 the stream is tuned so Day 3 survives by 5.00 — almost
certainly deliberate on the setter's part, and a reason to be confident the
three-fee answer is the intended one.

Only AED is configured. BHD is absent on purpose (AMBIGUITIES.md §8): a fee
of "25.000 BHD" would be ~6× the AED value and an FX conversion would need a
rate the spec doesn't give.

### `DAILY_INTEREST_RATE = Decimal("0.0004")` — *given* as 0.04%/day

Stored as a fraction, not a percentage, so `balance * rate` is the accrual
with no further division. Plausibility: 0.04%/day ≈ 14.6% simple p.a.
(15.7% compounded daily). High for a current account, plausible for a toy;
the direction (credit interest on positive balances) is clear.

**Half it (0.0002):** the ACC-001 schedule becomes 0.05 / 0.05 / 0.13 / 0.08
/ 0.08 / 0.08 = 0.47, and BHD Day 5–6 accruals 0.002 each. All still
non-zero, so the scenario still exercises every rounding path — and at this
rate two exact ties appear (225 × 0.0002 = 0.045, 625 × 0.0002 = 0.125), so
the rounding-mode choice above would start to matter. **Double it:**
0.20 / 0.18 / 0.50 / 0.33 / 0.31 / 0.31 = 1.83. No branch in the code depends
on the rate's magnitude, which is the point of this check: the rate is pure
data.

A common bug this guards against: writing `0.04` and multiplying — that is
4%/day, 100× too much. The test `test_expected_schedule_and_total` pins the
0.93 figure and would catch it.

### `WINDOW_DAYS = 6` — *given*

**Half it (3):** E4, E5–E10 would never run and the whole backdating problem
vanishes; the exercise would be trivial. The window is exactly long enough
for a backdated entry (Day 5 → Day 2) and its reversal (Day 6 → Day 2) to
each rewrite three or four closed days. Not a free parameter.

### Day index base = 1

Days are 1..6 as in the brief, so a report line and the spec line match
without translation. Value dates are compared with `<=`, so the base is
irrelevant to the arithmetic. An opening balance, if there were one, would be
value_date 0 — one below the base, which is the only place the base shows.

### Overdraft threshold: balance `< 0` — *given* ("is negative")

Strict. A closing balance of exactly 0.00 is not overdrawn. Tested
(`test_zero_balance_is_not_overdrawn`). There is no "half" of a comparison;
the check is whether `<= 0` would be detected — it would, by that test.

### Interest threshold: balance `> 0` — *given* ("positive balances only")

Strict. Zero earns nothing, negative earns nothing (and is not charged debit
interest either — the spec is silent on that and I did not add it).

### Instalment count = 3 — *given* ("three equal instalments")

**Half it** isn't an integer; the meaningful check is `n = 1` (no split —
tested, returns `[10.000]`) and `n = 2` (5.000 / 5.000, no remainder). The
interesting case is any `n` that does not divide 10,000 fils: 3, 6, 7. The
conservation property is tested across n ∈ {1, 2, 3, 7} and 499 totals.

### Instalment remainder → last instalment

Could equally be first. "Last" keeps the first n−1 instalments at the literal
rounded-down quotient (3.333) and puts the single adjusted figure in a
predictable place. Changing it to "first" would flip the E10 entries to
3.334 / 3.333 / 3.333 and nothing else; the sum is invariant either way.

### `seq` starts at 1

Record sequence numbers are 1-based, monotonic across all three logs
(entries, auths, errors), never reused. Starting at 0 would be fine; 1 reads
better in a log. The property that matters — strictly increasing — is tested.

### Capitalisation day = `WINDOW_DAYS` — *given* ("end of Day 6")

Interest is capitalised once, in the last day's close. A monthly or
end-of-cycle rule would make this a schedule rather than a constant.
**Half it** (Day 3) would capitalise 0.46 on Day 3, which would then earn
interest on Days 4–6 — compounding inside the window, which the spec does
not describe.

---

### Numbers that are *not* constants

- **−370.00, −395.00, 5.00, −155.00, 0.93, 390.93, 10.008** and friends
  appear only in tests and docs. They are derived from the stream and the
  constants above and are pinned so a regression is loud.
- **14 ledger entries, 2 auth records, 1 error record** at window end:
  likewise pinned (`test_record_counts_and_append_only`).
- There is no tolerance, epsilon, retry count, cache size or timeout anywhere
  in the code. Decimal arithmetic needs no epsilon, and an in-memory core
  needs no retries.
