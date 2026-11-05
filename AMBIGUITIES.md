# AMBIGUITIES

Every place the brief under-specifies, what the options were, which one the
code takes, and where. Numbered so REJECTED.md and the code can refer to them.

Legend: **Chose** = what the code does. **Where** = file / function.

---

## 1. Posting day vs value date — are they the same clock?

The event list gives each event a "Day N" *and* a value_date. For most events
they coincide. For E7 and E9 they don't. The brief never says what "the
Day 2 closing balance" means once a Day-5 event has value_date Day 2.

Options: (a) ignore value_date and use posting day; (b) use value_date for
balances and treat posting day as the replay order only; (c) keep both and
make every balance question explicit about which clock it is asking in.

**Chose (c).** `Ledger.balance(account, value_date_upto, as_of_posting_day)`.
"Day 2 as the Day 2 close saw it" is `balance(a, 2, as_of_posting_day=2)` =
250.00. "Day 2 as known at end of Day 5" is `balance(a, 2, as_of_posting_day=5)`
= −370.00 (before fees). Both are correct answers to different questions;
criterion 1 asks the second one. **Where:** `ledger/ledger.py`.

## 2. When a backdated entry lands, do already-closed days get re-assessed for fees?

The rule: "assessed once per day per account when that day's closing ledger
balance (all entries with value_date ≤ that day) is negative."

Options: (a) assess only the current processing day at each close; (b) at
each close, re-assess every day ≤ today against the ledger as known now;
(c) read "once per day" as *once per close* — at most one fee per account per
processing day, whatever the history looks like.

**Chose (b).** Three reasons, in order of weight:

1. The parenthetical "all entries with value_date ≤ that day" is a value-date
   definition of the balance being tested; the only way to honour it after E7
   is to re-examine Days 2–4 on Day 5.
2. Criterion 1 itself: "the Day 2 closing ledger balance, evaluated at end of
   Day 5 **and before any fee is assessed**". That qualifier only has any
   effect if a fee assessed at the end of Day 5 can land on Day 2. Under (a)
   no fee can ever touch Day 2 and the words are dead; the setter wrote them,
   so the setter expects a Day-2 fee to be booked on Day 5.
3. Under (a) the Day 2 and Day 4 closes sit at −395 / −205 by value date with
   no fee against them, which the rule's own definition says cannot happen.

Days are walked ascending so the Day 2 fee is in the Day 3 balance before
Day 3 is judged. Idempotent: a second run books nothing. (a) is engine v1
(REJECTED.md Part 2A). (c) grammatically detaches "once per day" from "that
day's closing balance", and even under (c) the single fee would be for Day 5,
not Day 2 — it rescues no criterion. **Where:** `Engine.end_of_day_fees`.

## 3. Fee value_date: "the day assessed" — assessed *for* or assessed *on*?

"Booked with value_date equal to the day assessed." The Day 2 overdraft is
discovered and the fee booked on Day 5. Is the fee's value_date Day 2 (the
day that was assessed) or Day 5 (the day the assessment ran)?

**Chose Day 2** (the day being assessed *for*). The plain-English case for
Day 5 is real — "the day [the fee is] assessed" can mean the day the
assessment ran — so this rests on evidence, not grammar: criterion 1 qualifies
the Day 2 balance with "before any fee is assessed", which presupposes a fee
that lands on Day 2 (see §2); criterion 2, wrong as it is about the count,
places the fee "on Day 2"; and in value-dated banking a charge caused by a
day's balance carries that day's value date so that interest from that day
reflects it. Dating it Day 2 also keeps "that day's closing balance"
self-consistent (Day 2 ends at −395.00). The posting_day records Day 5
separately, so nothing is lost.

Consequence worth knowing: it does **not** change which days get fees in
this stream — with value_date Day 5 instead, Days 2, 4 and 5 are still the
negative ones. It changes the restated Day 2–4 balances (250 / 650 / 465
instead of 225 / 625 / 415) and therefore the interest: 0.97 instead of
0.93, final 390.97 instead of 390.93. Four fils. One coupling to be aware of: the
once-per-day latch is keyed on the fee's `ref` (`overdraft:<day>`), not its
value_date, precisely so that the alternative reading would still latch the
right day (a Day-2 fee value-dated Day 5 must not block the Day-5 fee).
**Where:** `Engine.end_of_day_fees`, `Ledger.fee_for`.

## 4. Does the fee itself count toward "that day's closing balance"?

A fee with value_date Day 2 makes Day 2 even more negative. Does that trigger
another fee? No: "once per day per account" is enforced as a lookup on
(account, fee value_date), so the fee is a one-way latch. It also means
the fee does *not* unwind when the day later turns positive — see §10.
**Where:** `Ledger.fee_for`.

## 5. Order of end-of-day operations

Nothing says whether fees run before interest, or whether the last day's
accrual sees the capitalised credit.

**Chose:** events → fees → (last day only) interest schedule → capitalisation.
The Day 6 accrual is taken on the Day 6 closing balance *before* the interest
credit lands; the credit then posts with value_date Day 6. The overdraft check
on Day 6 ran before the credit, so interest can never rescue a day from a fee.
**Where:** `Engine.run_day`, `Engine.capitalize_interest`.

## 6. Is interest recomputed for past days after a backdated entry?

Same question as §2, for accruals. Options: (a) freeze each day's accrual at
that day's close; (b) derive the whole schedule from the final value-dated
history.

**Chose (b).** The spec says accruals are "on the closing ledger balance",
which after E7/E9 means the restated one. More fundamentally: in banking the
value date *is* the interest-effective date — that is what the concept is
for. A debit value-dated Day 2 is a statement that the money left on Day 2
for interest purposes, and interest for Days 2 onward is recomputed. A system
that freezes each day's accrual on what it knew that evening has value dates
in name only. (a) was engine v1 and gave a capitalised figure (0.83; 0.81 in
v2 once fees were right) that blended three different beliefs about Day 2.
The per-day report still prints an "accrued to date (provisional)" figure
so a reader can watch it fall on Day 5 and recover on Day 6. **Where:**
`Engine.interest_schedule`.

## 7. Round daily, or accrue exactly and round once?

0.04% of 415.00 is 0.166. Round each day (→ 0.17) and sum, or sum the exact
figures (0.918) and round once (→ 0.92)? The two differ by one fils over
six days.

**Chose round daily, then sum (0.93).** The spec says "amounts stored and
rounded to their own precision" and "the rounded daily accruals must sum
exactly to the capitalized total"; both point at daily rounding with the
total defined as the sum. Round-once is the more common bank convention and
would be my pick without that wording; it needs a "last day absorbs the
difference" rule, which the spec does not supply. Criterion 8's "discard the
remainder" is wrong under either convention. **Where:**
`Engine.interest_schedule`, `Engine.capitalize_interest`.

## 8. What is the overdraft fee for a BHD account?

The spec gives "AED 25.00". It does not give a BHD fee or an FX rule.

**Chose:** fees are a per-currency table; BHD is absent. If ACC-002 ever
closes negative the engine books nothing and records a `FEE_NOT_CONFIGURED`
error rather than converting 25.00 AED at an invented rate or applying 25.000
BHD (about 6× the value). Never triggered in the stream. **Where:**
`engine.OVERDRAFT_FEE`, `Engine.end_of_day_fees`.

## 9. A settlement with no authorization (E6)

Not specified by the rules; criterion 4 supplies "reject, no funds move".
**Chose:** reject with an `ERROR` record. The force-post counter-argument is
in REJECTED.md (criterion 4 note). **Where:** `Engine._settle`.

## 10. A reversal of an entry that triggered fees (E9 after E7)

Does reversing the cause unwind the fees? The spec does not say; criterion 6
assumes the answer is yes and that it happens by values "returning".

**Chose:** no automatic unwind. The reversal is a compensating entry for the
target only. Fees remain. This is the subject of the one failing test and of
REJECTED.md (criterion 6): the honest version of "yes" is a compensating
fee-reversal rule, which I did not invent. **Where:** `Engine._reverse`,
`tests/known_limitation_test.py`.

## 11. Does a reversal re-run authorizations that were declined because of the reversed entry?

Auth-B was declined on Day 5 because E7 had made available −155.00. After E9
the same request would have been approved. **Chose:** no. An authorization is
a decision at a moment on the ledger as known then; the merchant received a
decline. Revisiting it would mean the ledger issuing approvals nobody asked
for. **Where:** `Engine._authorize`; asserted in `test_scenario.py`
(`test_declined_auth_is_not_reopened_by_e9`).

## 12. Which instalment absorbs the rounding remainder?

10.000 / 3 leaves 0.001. Three options: put the remainder on the last
instalment; put it on the first; or treat "three *equal* instalments" as
literally impossible at BHD precision and reject E10 as malformed.
**Chose:** the last instalment (3.333, 3.333, 3.334), so the first n−1 are
the literal equal quotient and the adjustment is in one predictable place.
First-instalment is equally valid; the sum is what matters. Rejecting the
event is what a strict reading of "equal" demands, but it is not how
instalment plans work anywhere — the plan conserves the total and documents
which instalment absorbs the rounding. **Where:** `money.split_equal`.

## 13. Are three instalments three entries or one?

**Chose:** three CREDIT entries sharing `origin_event = "E10"`, each with a
`memo` of `instalment i/3`, same value_date. Consequence: a reversal of E10
reverses all three (tested). One entry of 10.000 would make "posted as three
instalments" meaningless.

## 14. Replay "in this order" when the listing is not in day order

The listing has E9 (Day 6) before E10 (Day 5). "Replayed in this order" could
mean literally (process a Day 6 event, then a Day 5 one) or grouped by day
with the listing as the tiebreak.

**Chose:** grouped by posting day, listing order within a day (E7, E8, E10 on
Day 5; E9 on Day 6). Processing a Day 6 event before Day 5 has closed would
make the Day 5 close include Day 6 knowledge. Outcome is identical here
because E9 and E10 touch different accounts, but the rule has to be stated.
**Where:** `Engine.run_events`.

## 15. Are debits ever declined?

Only authorizations have an approval test in the spec. **Chose:** debits
always post, even into overdraft — they are cleared items, and the overdraft
fee exists precisely because the balance can go negative. The authorization
gate is the only place funds are refused. **Where:** `Engine._debit`.

## 16. Settlement for more than the hold

E5 settles 185 against 200. What if it were 215? **Chose:** post it and
record an `OVER_SETTLEMENT` warning. Card schemes tolerate over-settlement
within limits (tips, fuel). Rejecting would again put the ledger at odds
with the money. **Where:** `Engine._settle`; tested.

## 17. Future-dated value dates

None in the stream. **Chose:** the store refuses `value_date > posting_day`
(`LedgerError`). Allowing them would make "balance as of day d" ambiguous
(do future-dated entries count toward today?). A real system would accept and
exclude them; here it is simpler and safer to make them impossible.
**Where:** `Ledger.append_entry`.

## 18. "Available balance" — which clock?

"ledger balance minus active holds" — but ledger balance as of when?
**Chose:** value_date ≤ today, as known today, minus holds approved and
unsettled as of today. It is the authorizer's view at the moment of decision.
**Where:** `Ledger.available`.

## 19. Does a declined authorization hold anything?

**Chose:** no; it is recorded (with the available-before/after that produced
the decline) but contributes nothing to held funds. **Where:**
`Ledger.active_holds`.

## 20. Unsettled holds at window end

Auth-B "is never settled inside the window" — moot, since it was declined.
Had it been approved it would still be ACTIVE on Day 6 and the report flags
`UNSETTLED at window end`. No expiry rule is specified; none is implemented.

## 21. Precision of inputs

"Amounts stored and rounded to their own precision." Rounded on input, or
refused if over-precise? **Chose:** refused. Every monetary amount on an
input event (credit, debit, hold, settlement) is checked in `Engine.apply`
before anything else happens, and the store checks entries again. A 3.3333
BHD posting is a bug upstream, not something to silently round. Computed
amounts (interest, instalments) are quantized by the code that computes them.
*Review note:* the first version checked only at the store, which credits
bypassed because `split_equal` quantizes before posting; caught by the
independent review, fixed, tested. **Where:** `Engine.apply`,
`Ledger.append_entry`, `money.quantize`.

## 22. Rounding mode

Not specified. **Chose:** ROUND_HALF_UP (commercial rounding). In this
stream no exact .5 tie occurs at the rounding digit (0.166 → 0.17 under both
half-up and banker's), so the choice is invisible here and would only show
up with other figures (e.g. at half the rate, NUMBERS.md). Stated so it is
not accidental. **Where:** `money.ROUNDING`; NUMBERS.md.

## 23. Opening balances

Both 0. **Chose:** no opening entry; an empty ledger sums to zero at the
currency's precision. A non-zero opening balance would be a CREDIT with
value_date 0. **Where:** `Ledger.__init__`.

---

The six below were raised by the independent review of the first complete
version (WORKLOG.md). §24–§27 are decisions the code had already taken
without saying so; §28 is a reading question; §29 is a design gap.

## 24. Three instalments — same value date, or spread over days?

"Posted as three equal instalments — value_date Day 5." Read as three
postings all value-dated Day 5. The other reading (Day 5 / Day 6 / Day 7)
would put the third instalment outside the window and leave ACC-002 at
≈ 6.670 with 0.004 interest. **Chose** same value date: the event states one
value_date, and an instalment *plan* would need a schedule the brief does not
give. **Where:** `Engine._credit`.

## 25. A reversal's value date must equal its target's

E9 states value_date Day 2, which is E7's. The engine *requires* that
equality and rejects a reversal with any other value_date
(`VALUE_DATE_MISMATCH`). The alternative — a reversal value-dated on its own
posting day (Day 6) — would leave Days 2–5 restated negative and change the
fee and interest picture entirely. A reversal that does not undo the original
by value date is a new transaction, not a reversal. **Where:**
`Engine._reverse`; tested.

## 26. Partial settlement: what happens to the unsettled 15.00?

E5 settles 185 against a 200 hold. **Chose:** the whole hold is released;
the auth is SETTLED and no longer active. The 15.00 does not stay held.
That matches single-clearing card behaviour (the clearing message closes the
authorization); multi-clearing (partial captures) would need the hold to
track a remaining amount, which is a different design. No effect on this
stream. **Where:** `Ledger.active_holds`, `Ledger.settlement_of`.

## 27. Which clock decides an authorization?

Holds are tested against the ledger as known on the *posting day* of the
authorization; `AuthRecord.value_date` is recorded but does not enter the
decision. A backdated authorization (none in the stream) would therefore be
decided on today's view, not on the balance as of its value date. **Chose**
that deliberately: an authorization is a question asked *now*; its value date
is bookkeeping. **Where:** `Engine._authorize`, `Ledger.available`.

## 28. Is the Day 6 closing balance 390.00 or 390.93?

Capitalisation happens "at end of Day 6" with value_date Day 6, so the Day 6
close *includes* it: 390.93. The pre-capitalisation figure (390.00) is the
one the Day 6 accrual is computed on and is visible in the schedule. Both are
printed. **Where:** `Engine.run_day`, `report.py`.

## 29. Reversing a settlement

Not in the stream. **Chose:** the reversal returns the funds (a +amount
REVERSAL entry) but does **not** reinstate the hold — the authorization stays
SETTLED and consumed, and a merchant who wants to charge again needs a new
authorization. This is pinned by a test so it cannot drift silently
(`test_reversed_settlement_returns_funds_but_does_not_reinstate_the_hold`).
A design that re-activates the hold would need `settlement_of` to ignore
reversed settlements; I did not want a reversal to silently create a live
hold. **Where:** `Ledger.settlement_of`.

## 30. Fees and interest: on ledger balance or available balance?

Both rules say "closing **ledger** balance", and the fee rule defines it as a
sum of *entries*; holds are not entries, and the authorization rule defines
available as "ledger balance minus active holds" — a different quantity. So
the text settles it: fees and interest are on the ledger balance; available
is used in exactly one place, the authorization decision. The economics
agree: a fee charges for money that actually left, and an open hold is money
that may never leave. On Day 2, with Auth-A open, available was 50.00 and the
fee check saw 250.00. Not an ambiguity so much as a confirmation, recorded
because it is the first thing a reader asks. **Where:** `Engine.end_of_day_fees`,
`Engine.interest_schedule`, `Ledger.available`.

## 31. Transactions approved before a backdated debit lands

The mirror of §11. Auth-A was approved on Day 2 against available 50.00; by
value date, once E7 lands, there was never money for it (Day 2 = −370). Its
settlement on Day 4 was posted when the balance showed 650; by value date it
took Day 4 from +30 to −155. **Chose:** they stand. Neither is re-evaluated,
reversed or flagged. An authorization is a decision made at a moment on the
information available then; a ledger that clawed back approved transactions
on later information would be unusable for the merchant side. The account
carries the exposure, and the fee cascade is the only mechanism the spec
offers in return. A production system would likely *flag* Auth-A as
"approved on a later-restated balance" for risk review without touching the
money; that is reporting, not a ledger-core rule. **Where:** `Engine._authorize`
(no re-run path exists).

---

## What each choice is worth

Final ACC-001 balance under the readings above, so a reader can see which
decisions move money and by how much. Every row was produced by running the
engine with that one reading swapped in (the script is not in the repo; the
figures are reproducible from the descriptions).

| Reading | Fees for | Restated D2–D5 | Interest | Final |
|---|---|---|---|---|
| **Chosen** — fee value-dated to the day assessed for (§3); accruals from restated history (§6) | 2, 4, 5 | 225 / 625 / 415 / 390 | 0.93 | **390.93** |
| Fee value-dated to the day the assessment ran (§3 alternative) | 2, 4, 5 | 250 / 650 / 465 / 390 | 0.97 | 390.97 |
| Accruals frozen at each day's own close (§6 alternative, engine v2) | 2, 4, 5 | 225 / 625 / 415 / 390 | 0.81 | 390.81 |
| Current-day-only fee check + frozen accruals (engine v1) | 5 | 250 / 650 / 465 / 440 | 0.83 | 440.83 |
| Criterion 4 rejected — E6 force-posted as a flagged debit (§9 alternative) | 2, 4, 5 | 225 / 625 / 235 / 210 | 0.69 | 210.69 |
| Criterion 6's intent — fees unwound by E9 (§10 alternative) | none net | 250 / 650 / 465 / 465 | 1.03 | 466.03 |

What does not move under any reading that re-examines past days: three fees
(Days 2, 4, 5), the Day 5 close at −230.00, Day 6 at 390.00 before interest,
Auth-B declined, E6 rejected, 3.333 / 3.333 / 3.334, and BHD 10.008.
