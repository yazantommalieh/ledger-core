# REJECTED

Part 1 — acceptance criteria refused, with reasons.
Part 2 — approaches abandoned mid-build.

Numbers below come from `python3 replay.py`; the tests in
`tests/test_scenario.py` assert each verdict.

---

## Part 1 — Acceptance criteria

The brief lists eight. Verdicts:

| # | Criterion (abridged) | Verdict |
|---|---|---|
| 1 | Day 2 close, evaluated end of Day 5, before fees = AED −370.00 | **Accepted** |
| 2 | E7 causes exactly one overdraft fee, on Day 2 | **Rejected** |
| 3 | Day 4 settlement of Auth-A must be accepted | **Accepted** |
| 4 | Settlement with unknown auth id is rejected, no funds leave | **Accepted** (policy choice; see note) |
| 5 | If Auth-B is approved, its hold reduces available, not ledger | **Accepted** as a statement; premise is false (Auth-B is declined) |
| 6 | After E9, all balances and fees return to pre-E7 values | **Rejected** |
| 7 | The three BHD instalments must each be 3.334 | **Rejected** |
| 8 | If rounded accruals don't sum to the capitalised total, discard the remainder | **Rejected** |

### Criterion 2 — "E7 causes exactly one overdraft fee to be assessed, on Day 2"

**Rejected on both counts: the count and the day.**

The fee rule is defined on value-dated closing balances: *"assessed once per
day per account when that day's closing ledger balance (all entries with
value_date ≤ that day) is negative."* E7 is a 620.00 debit with value_date
Day 2, posted Day 5. By value date it changes every close from Day 2 onward:

| Day | before E7 | after E7, before fees | after fees |
|---|---|---|---|
| 2 | 250.00 | −370.00 | −395.00 ← fee |
| 3 | 650.00 | 30.00 | 5.00 (positive, no fee) |
| 4 | 465.00 | −155.00 | −205.00 ← fee |
| 5 | 465.00 | −155.00 | −230.00 ← fee |

Three days are negative, so three fees. "Exactly one" is false under any
reading of the rule that honours "all entries with value_date ≤ that day".

"On Day 2" is also misleading. The fee *for* Day 2 carries value_date Day 2,
but it is *assessed* (posted) on Day 5, because Day 5 is when the ledger first
learns that Day 2 was overdrawn. The report shows both dates.

The only design under which the criterion is close to true is one that never
re-examines a closed day (engine v1, Part 2 below): that yields one fee — but
for Day 5, not Day 2, and it violates the rule's value-date definition.

### Criterion 6 — "After E9, all balances and fees return to their pre-E7 values"

**Rejected as stated.** "Return to their pre-E7 values" describes a
mutation; in an append-only log nothing returns, things are compensated. The
criterion's intent is reachable (see below) but only through a rule the spec
does not state, and the mechanism it names is not available.

E9 is a reversal, which in an append-only ledger means a *compensating entry*:
+620.00 with value_date Day 2, posted Day 6. E7 is not removed. After E9:

- The **transactional** balances do return: 1200 − 950 − 620 + 620 = 250 on Day 2.
- The **fees do not**. The three 25.00 FEE entries booked in the Day 5 close
  are records; they cannot be deleted, and nothing in the spec says they are
  reversed. So every value-dated balance from Day 2 on is lower than pre-E7
  by the cumulative fees: Day 2 is 225.00 (not 250.00), Day 4 is 415.00 (not
  465.00), Day 5 is 390.00.
- **Auth-B stays declined.** Authorizations are decisions made at a moment on
  the ledger as known then; a later reversal does not re-run them.
- **Interest changes**, because it accrues on the restated balances.

Could the design reverse the fees too? Yes. The fee rule is a predicate on
value-dated closing balances, and after E9 that predicate is false for Days 2,
4 and 5. The engine already re-assesses past days in one direction (book a
fee when a day turns negative); the symmetric direction (book a compensating
FEE_REVERSAL when a fee'd day turns positive) is perfectly append-only, and
after it every value-dated *balance* would match pre-E7 and net fees would
be zero. So the criterion is **satisfiable in intent**. What it is not is
*specified*: the brief gives no fee-reversal rule, and whether such reversals
are automatic or an ops decision is a product question I should not settle
inside a ledger core. I did not implement it, and the one deliberately failing
test (`tests/known_limitation_test.py`) exists to make that gap loud rather
than quiet. Honest summary: *not implemented, needs an unstated rule* — not
*impossible*. Auth-B's decline would still stand either way (§11 of
AMBIGUITIES.md).

### Criterion 7 — "The three BHD instalments in E10 must each be BHD 3.334"

**Rejected.** 3 × 3.334 = 10.002. The event is a credit of 10.000; posting
10.002 creates 0.002 BHD from nothing. The instalments are 3.333, 3.333 and
3.334 (quotient rounded down, remainder on the last instalment —
`money.split_equal`). `sum(parts) == total` is asserted in code.

### Criterion 8 — "If the rounded daily interest accruals do not sum to the capitalised total, the remainder is discarded"

**Rejected.** It contradicts the non-negotiable rule *"the rounded daily
accruals must sum exactly to the capitalized total"* and it discards money.

There is no remainder to discard because the capitalised total is *defined*
as the sum of the rounded daily accruals: 0.10 + 0.09 + 0.25 + 0.17 + 0.16 +
0.16 = 0.93 for ACC-001. The alternative — accrue at full precision, round
once at the end (0.918 → 0.92) — is a legitimate banking convention, but the
spec's wording rules it out, and *that* convention still never discards
anything: it adjusts one day's accrual to absorb the difference. Either way,
"discard" is wrong. See AMBIGUITIES.md §7 for why 0.93 and not 0.92.

### Criterion 4 — note on why it is accepted, and the case against it

The spec does not say what to do with a settlement that has no authorization.
This criterion fills the gap with a rule (reject, no funds move), and the
rule is internally consistent with the rest of the spec, so I accept it and
E6 is rejected with an `ERROR` record.

For the record, the real-world counter-argument: in card schemes a clearing
record with no matching authorization (a "force post") still debits the
cardholder — the issuer owes the network regardless, and the dispute happens
afterwards through chargeback. A ledger that refuses it is a ledger that
disagrees with the money. If this core sat under a real card programme I
would post E6 as a debit flagged `NO_AUTH` rather than drop it. For this
exercise the criterion's rule is clear and I follow it.

### Criterion 5 — note on the trap

The statement is true for every authorization in this ledger: a hold reduces
available balance only. But "if Auth-B is approved" is doing a lot of work.
By the time E8 arrives on Day 5, E7 has already been posted; available is
−155.00 and a 90.00 hold would take it to −245.00. Auth-B is **declined**.
An implementation that approves it has either ignored E7 when computing
available (e.g. by using a Day-4 cached balance) or is not applying backdated
entries to the current view.

---

## Part 2 — Approaches abandoned mid-build

A and B were committed and then replaced — both are in the history. C and
D were rejected before any code was written, so they exist only here.

### A. Current-day-only fee assessment (engine v1, commit `135e535`)

End-of-day looked at `balance(account, today)` and booked a fee if negative.
Simple, and it is how a system without value dates would work.

Abandoned because the rule is defined on *"that day's closing ledger balance
(all entries with value_date ≤ that day)"*. After E7 lands on Day 5, Days 2
and 4 are negative by that definition and v1 never looks at them again. It
produced one fee (Day 5) instead of three and left Day 2 un-fee'd while the
spec's own criterion 1 insists the Day 2 close is −370.00 "evaluated at end
of Day 5". Replaced by re-assessing all days ≤ today at every close
(engine v2, commit `4bbcb30`), which is idempotent thanks to the
once-per-day lookup.

### B. Per-day stored interest accruals (engine v1, same commit)

Each close computed that day's accrual on that day's balance and stored it
in a dict; Day 6 summed the dict.

Abandoned because a stored accrual is a cached derivative of a balance that a
backdated entry can change. After E7 the stored Day 2–4 accruals (0.10, 0.26,
0.19) described balances that no longer existed by value date; after E9 they
were wrong in the other direction. The capitalised figure was a blend of
three different views of history: 0.83 in v1, and still 0.81 in v2 after the
fee fix, against 0.93 from the restated history. Replaced by deriving the
schedule from the ledger on demand (`Engine.interest_schedule`, engine v3,
commit `50594de`), which gives 0.93 and is correct by construction.

I briefly considered keeping the stored accruals and *booking* each day's
accrual as a ledger entry, then compensating on restatement. That is a
defensible design for a real core (it gives an audit trail of what was
believed when) but it multiplies entries and reintroduces exactly the
"compensate the derived entry" machinery that fees lack (see the failing
test). Out of scope here.

### C. Running balance per account

Rejected before the first line of code, so no commit — but worth stating.
A `balance` field that is incremented on each posting is the normal way to
build a ledger and it is wrong for this one: it answers "what is the balance
now" and nothing else. The assignment asks "what was the Day 2 balance, as
known on Day 5". That requires the balance to be a *query* with two
parameters (value date, as-of posting day), which is what `Ledger.balance`
is. Cost: O(n) per query. For an in-memory core with 14 entries that is
nothing; for a real one it is where an indexed projection goes.

### D. Mutable hold state

Early sketch had `AuthRecord.status` flipping APPROVED → SETTLED. Dropped
before commit because it is a mutation of a record. Replaced by deriving the
state: an approved auth with no settlement entry referencing it is active.
The settlement entry *is* the state change.
