# ledger-core

An in-memory, append-only account ledger core with value-dated balances,
overdraft fees, daily interest accrual and card-style authorizations/holds.

No web layer, no persistence, no UI, no database, no third-party packages.
Python 3.10+, standard library only (`decimal`, `dataclasses`, `unittest`).

## Run it

```
python3 replay.py              # replay the six-day event stream, print the per-day report
make test                      # the green suite (67 tests)
make test-known-limitation     # the one test that FAILS BY DESIGN
make test-all                  # both, in that order
```

Without `make`:

```
python3 -m unittest discover -s tests -p 'test_*.py' -v     # green suite
python3 -m unittest tests.known_limitation_test -v          # the failing one
```

The failing test lives in `tests/known_limitation_test.py` — named outside
the `test_*.py` pattern so the green suite stays green and the red one is
red on purpose. Every assertion in it is annotated with what the failure
reveals about the design.

## Read the output

`replay.py` prints one block per day:

```
=== Day 5 ===
Events                       each event with its outcome (POSTED / APPROVED / DECLINED / REJECTED)
History restated ...         earlier days whose value-dated balance this day's postings changed
Overdraft fee assessments    fees booked in THIS close, with value_date and posting day
Closing ledger balance       entries with value_date <= today, as known today
                             (+ available balance when a hold is active; + provisional interest accrued)
Authorization states         ACTIVE / SETTLED / DECLINED, with hold and settlement amounts
Errors / warnings            rejected events and flags recorded today
```

Day 6 additionally prints the final interest accrual schedule and the
capitalised credit; a window summary closes the run.

**Where to look first:** the Day 5 block. E7 (a 620.00 debit posted Day 5
with value_date Day 2) restates Days 2–4, triggers three overdraft fees in one
close, and declines Auth-B. The Day 6 block shows E9 reversing E7 and
restating history again — with the three fees still there.

## Final numbers

| | ACC-001 (AED) | ACC-002 (BHD) |
|---|---|---|
| Restated closing balances D1–D6 | 250.00 / 225.00 / 625.00 / 415.00 / 390.00 / 390.93 | 0 / 0 / 0 / 0 / 10.000 / 10.008 |
| Overdraft fees | 3 (for Days 2, 4, 5; all assessed in the Day 5 close) | 0 |
| Interest schedule | 0.10 / 0.09 / 0.25 / 0.17 / 0.16 / 0.16 | 0 / 0 / 0 / 0 / 0.004 / 0.004 |
| Capitalised Day 6 | 0.93 | 0.008 |
| Final ledger balance | **390.93** | **10.008** |
| Auth-A | SETTLED (185.00 against a 200.00 hold, Day 4) | |
| Auth-B | DECLINED (available −155.00 at Day 5) | |
| E6 (Auth-Z) | REJECTED, no funds moved | |

## Layout

```
ledger/
  money.py      precision table, HALF_UP rounding, conserving instalment split
  events.py     frozen input events; each carries posting_day AND value_date
  ledger.py     append-only store; balance(account, value_date_upto, as_of_posting_day)
  engine.py     day-by-day replay; end-of-day fee re-assessment; interest schedule
  report.py     text rendering of per-day reports
  scenario.py   the assignment's accounts and event stream, as data
replay.py       runner
tests/
  test_money.py, test_ledger.py, test_engine_edges.py, test_scenario.py
  known_limitation_test.py        <- the deliberately failing test
NUMBERS.md      every constant, why that value, what "half it" would do
AMBIGUITIES.md  23 under-specified points and how each was resolved
REJECTED.md     the 4 acceptance criteria refused (and why), and 4 abandoned approaches
WORKLOG.md      timestamped log of the build; the commit history is the other half
```

## The one idea

Every event has two dates. `posting_day` is when the ledger *learns* about it;
`value_date` is when it is *effective*. "The Day 2 closing balance" is
therefore a function of when you ask: 250.00 on the evening of Day 2,
−370.00 on Day 5 after E7 lands, 225.00 on Day 6 after E9 lands (the 25.00
difference from 250.00 is the Day 2 overdraft fee, which is a record and does
not go away). `Ledger.balance(account, value_date_upto, as_of_posting_day)`
is the single primitive everything else is built on; there is no running
balance anywhere.

Consequences the code takes seriously:

- **Fees are re-assessed for every day ≤ today at every close**, against the
  ledger as known now, once per (account, day). A backdated debit can and
  does fee three days at once.
- **Interest is derived, never stored.** The schedule is recomputed from the
  final value-dated history; the capitalised credit is the sum of the rounded
  daily accruals by construction.
- **Reversals are compensating entries.** E9 adds +620.00 at value_date Day 2;
  E7 stays in the log. Fees E7 caused stay too — see the failing test and
  REJECTED.md for why that is the honest answer and what a fix would need.
- **Holds never touch the ledger balance**; their state (active / settled /
  declined) is derived from the log, not stored.

## Acceptance criteria verdicts

Accepted: 1, 3, 4 (as a policy choice), 5 (as a statement; its premise is
false — Auth-B is declined). Rejected: 2, 6, 7, 8. Full reasoning in
REJECTED.md; each verdict is a test in `tests/test_scenario.py`.

## How this was built

With Claude (Anthropic) as pair-programmer, as the brief allows. WORKLOG.md
says who did what and when; the commit history is intact and unsquashed,
including the two approaches that were committed and then replaced.
