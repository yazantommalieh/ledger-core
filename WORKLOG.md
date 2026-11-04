# WORKLOG

All times are Asia/Dubai (UTC+4). Entries are appended as the work happens,
never rewritten afterwards. The commit history is the other half of this log.

**Tooling disclosure:** this repository was built in a single working session
using Claude (Anthropic) as a pair-programmer, as the assignment permits.
Yazan supplied the assignment, asked for a walkthrough of the problem, agreed
the approach, and reviewed the results; Claude wrote the code and the first
draft of every document in this repo. Entries below say who did what.

---

## 2026-11-04

- **11:26** — Yazan pastes the assignment and asks for an explanation of what
  is being tested. Claude's read: the whole exercise hinges on two clocks
  (posting day vs value_date), with E7 and E9 as backdated entries; four of
  the eight acceptance criteria contradict the non-negotiable rules.
- **11:43** — Yazan: "please do". Build starts. Plan agreed: Python 3 +
  `decimal`, stdlib `unittest`, one package `ledger/`, a `replay.py` runner,
  real commits per stage, docs written as decisions are made rather than at
  the end.
- **11:46** — Repo scaffolded (`git init`, `.gitignore`, README stub, this
  file).
- **11:52** — `ledger/money.py` + tests. Decisions taken here: Decimal only,
  ROUND_HALF_UP, precision table is a hard lookup (unknown currency raises
  rather than defaulting to 2dp), instalment split rounds down and puts the
  remainder on the last instalment. 12 tests green. First place criterion 7
  (3 x 3.334) is contradicted by code: `split_equal(10.000, 3, "BHD")`
  returns 3.333/3.333/3.334.
- **11:49** — `events.py` (frozen input events, two dates each) and
  `ledger.py` (append-only store). Design decision that shapes everything
  after it: no running balances, no mutable hold state. `balance(account,
  value_date_upto, as_of_posting_day)` is the single primitive — the second
  argument is what makes "Day 2 as seen on Day 2" and "Day 2 as seen on Day 5"
  two different, both-correct answers. Hold state is derived (approved auth
  with no settlement referencing it). Rejections are records too. Future-dated
  value_dates are refused at the store (none in scope; keeps balance-as-of
  unambiguous). 27 tests green.
- **11:50** — `scenario.py` (the stream as data) and `engine.py` **v1**:
  end-of-day checks only the current day's close for the overdraft fee, and
  stores each day's interest accrual as computed that evening. Ran it against
  the stream. It works mechanically, and it is wrong in two ways that the
  spec's own wording rules out:
  1. After E7 (posted Day 5, value Day 2) the restated Day 2 close is −370.00
     and Day 4 is −155.00, yet only Day 5 gets a fee. The rule says the fee is
     assessed when "that day's closing ledger balance (all entries with
     value_date ≤ that day) is negative" — a value-date definition. A fee
     engine that only ever looks at "today" cannot honour it.
  2. The Day 2–4 accruals (0.10 / 0.26 / 0.19) were computed on balances that
     no longer exist by value date; the capitalised 0.83 mixes stale and
     current views.
  Committing v1 as the abandoned approach (see REJECTED.md) before replacing
  end-of-day with a retroactive re-assessment.
- **11:51** — Engine **v2**: end-of-day re-assesses the overdraft fee for
  every day 1..today against the ledger as known today; fee value_date = the
  day being assessed, posting_day = today. Walked ascending so the Day 2 fee is
  in the Day 3 balance (Day 3 ends at +5.00, no fee). Result on the stream:
  fees for Days 2, 4, 5, all booked in the Day 5 close; restated ACC-001
  history 250 / 225 / 625 / 415 / 390. Verified idempotent (second run books
  nothing). Interest still wrong — 0.81 from stale per-day snapshots. Next.
- **11:51** — Engine **v3**: dropped the stored per-day accruals. The
  interest schedule is now a pure function of the ledger as known at a given
  day (`interest_schedule(acct, upto_day)`), computed on demand; capitalisation
  books the sum of the rounded daily accruals, so schedule == credit by
  construction. Per-day report gains "accrued to date (provisional)" and a
  "restated" block showing which earlier days a close rewrote. Stream result:
  ACC-001 0.93 (0.10/0.09/0.25/0.17/0.16/0.16), ACC-002 0.008; finals
  390.93 and 10.008. Noted for AMBIGUITIES: rounding once at the end instead
  would give 0.92 — the two readings differ by one fils.
- **11:52** — `report.py` + `replay.py`. Per-day block prints: events with
  outcome, history restated (before -> after per value date), fee assessments
  with both dates, closing balance (+ available when a hold exists), auth
  states, errors; Day 6 adds the accrual schedule and capitalisation; a window
  summary closes. Reading the Day 5 block is the fastest way to see the
  problem the assignment is really about.
- **11:54** — `tests/test_scenario.py` (one class per acceptance criterion;
  rejected ones asserted in corrected form with the original wording quoted)
  and `tests/test_engine_edges.py` (rejection paths the stream never hits:
  settle-twice, settle a declined auth, duplicate auth id, over-settlement
  flagged, reversal-of-reversal, reversal of an instalment credit, fee on
  zero balance, unconfigured-currency fee, capitalisation excluded from its
  own day's accrual). Two of my first edge assertions forgot that a 3-day
  mini-window capitalises interest on Day 3 (90.12 vs 90.00) — fixed the
  tests, not the engine; the engine was right. 67 green.
- **11:54** — The required failing test: `tests/known_limitation_test.py`.
  It asserts that reversing E7 unwinds the three fees E7 caused and reopens
  Auth-B. It fails on the first assertion (3 fees still booked) and the
  annotations explain the other two. Named outside the `test_*.py` pattern so
  the green suite stays green; `make test-known-limitation` runs it red on
  purpose, `make test-all` runs both. Added the Makefile.
- **11:58** — Documents. REJECTED.md: verdicts on all eight criteria
  (2, 6, 7, 8 refused; 4 accepted with the force-post counter-argument
  written down; 5 accepted as a statement with its false premise called out)
  plus four abandoned approaches (two of them real commits). AMBIGUITIES.md:
  23 numbered items, each with options / choice / where-in-code. NUMBERS.md:
  every constant with the half-it check — ran the engine at fee 12.50 and
  50.00 and at rate 0.0002 and 0.0008 to make sure the claimed figures are
  real, and caught my own arithmetic slip on the doubled-fee cascade
  (−305/−355, not −310/−360) by doing so. README rewritten with run
  instructions, how to read the output, and the final numbers table.
