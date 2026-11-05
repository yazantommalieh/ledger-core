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
- **12:25** — **Independent review.** Claude spawned a second, separate
  agent that had not seen the build, with the spec and the instruction to
  recompute the stream by hand and audit the docs against the code. Its hand
  calculation matched the program exactly. It found:
  - *Code:* credits bypassed the precision check (routed through
    `split_equal`, which rounds); `FEE_NOT_CONFIGURED` was re-reported at
    every close (6 records for a 3-day overdraft, not 3); `capitalize_interest`
    was not idempotent and the schedule changed if asked after capitalisation;
    `_reverse` ignored the event's own account field; `report.py` hard-coded
    day 6. All fixed in `0bbc4b9`, each with a pinning test (75 tests now).
  - *Docs contradicting code:* v1's capitalised figure was 0.83, not 0.81 (0.81
    was v2) — REJECTED.md and AMBIGUITIES.md §6 corrected; the "half it" claim
    for AED at 1dp was wrong (accruals coarsen, they don't vanish) — NUMBERS.md
    corrected; REJECTED.md Part 2 said all four abandoned approaches were
    commits when only A and B are; §22 was garbled; the failing test's
    annotated "unwound" balance was 465.93 and is 466.03 (verified by running
    with fees disabled).
  - *Criterion 6 framing:* the reviewer argued, correctly, that "contradicts
    append-only" overclaims — compensating fee reversals are append-only and
    would satisfy the criterion's intent. Reworded to "not implemented; needs
    an unstated rule", which is also what the failing test says.
  - *Six ambiguities missed* (instalment value dates, reversal value date
    rule, partial-settlement residual, which clock decides an auth, Day 6
    closing with/without capitalisation, reversing a settlement) — added as
    §24–§29.
  - *This file:* the money-layer entry above is stamped **11:52** but its
    commit (`e4ef48b`) is 11:47 and the entry after it is stamped 11:49. That
    stamp was typed by hand instead of read from the clock. Per this file's
    own rule it is not rewritten; this note is the correction, and every stamp
    from the 11:49 entry on came from `date`.
- **15:42** — Repo copied to Yazan's Mac (`~/Software/ledger-core`). Suite
  and replay re-run there: green, same numbers. Commits re-authored from the
  placeholder `yazan@localhost` to Yazan's real email with `git filter-branch`
  (author/committer email only — every message, diff and timestamp is
  unchanged; hashes changed, so the six hash references in README, REJECTED
  and this file were updated to the new ones). Old→new map:
  5e62585→91a6b59, 2ac8d86→e4ef48b, ce0692e→19257b5, 135e535→91a5570,
  4bbcb30→98f7a67, 50594de→e2b74ec, 95fa2e5→4ab3c6c, eb45e75→9bf71ed,
  fff3971→74d2db2, 89c47fe→5c391b7, 751bd2d→0bbc4b9, 778f61c→05c6113.

## 2026-11-05

- **16:34** — **Re-evaluation at higher effort.** Yazan asked for the whole
  solution to be re-examined. Done cold: re-read every file, recomputed the
  six days by hand without the program, re-argued each criterion and each
  ambiguity from the spec text. Outcomes:
  - *Arithmetic:* hand calculation matches the program line for line. No
    number changed. Verdicts on all eight criteria unchanged.
  - *Code:* three input-integrity gaps, none reachable from the stream — a
    settlement naming a different account from its authorization posted to
    the wrong account (same family as the reversal bug the review found);
    non-positive amounts were accepted (a negative credit is a debit in
    disguise); duplicate event ids were accepted (a reversal would then undo
    both). All three now raise or reject, each with a test. 78 tests.
  - *Docs — arguments strengthened, not conclusions:* §2 and §3 now cite
    criterion 1's own "before any fee is assessed" as textual evidence that
    the setter expects a Day-2 fee booked on Day 5 (previously argued from
    "most natural meaning"); §2 adds and dismisses a fourth reading, "once
    per close"; §6 states the banking definition of value date (it *is* the
    interest-effective date), which is the real reason accruals are
    recomputed; §12 records "reject E10 as impossible to split equally" as a
    considered option. New §30 (fees and interest on ledger, not available)
    and §31 (pre-E7 approvals stand) — both came out of Yazan's questions on
    the 4th. REJECTED.md criterion 2 now shows the criterion failing under
    all four readings.
  - *New:* a "what each choice is worth" table closing AMBIGUITIES.md — the
    final balance under each rejected reading (390.97, 390.81, 440.83,
    210.69, 466.03 against the chosen 390.93), each produced by running the
    engine with that reading swapped in. It also lists what does not move
    under any reading. That table is the one-paragraph answer to "how
    sensitive is your result to your interpretation".
- **16:52** — **Part 2.** Yazan shared the second deliverable: a 2–4 page
  Architecture & Trade-offs PDF (append-only at scale; value-dated entries in
  a UAE bank + one go-live control; authorization lifecycle; what was cut).
  Drafted from the implementation (the O(n) `balance` scan, the global
  `_seq`, the missing expiry, the fee-linkage gap behind the failing test).
  Regulatory references were looked up before going in, not recalled: CBUAE
  Consumer Protection Standards Art. 8 timelines; Regulations 29/2011
  Annexure 2 fee caps and the >5% approval rule; PSD2 Art. 87(3); scheme hold
  expiry windows; and the AML law — which turned out to have been replaced by
  Federal Decree-Law No. 10 of 2025 (in force 14 Oct 2025), so the new one
  is cited. Source is `docs/architecture.html`, rendered with Chromium to
  `docs/architecture.pdf` (4 pages). The one control chosen: a backdating
  horizon with maker-checker.
- **21:24** — Yazan: "short and simple". Part 2 rewritten from 4 pages / 2,670
  words of dense tables to 2 pages / 1,600 words of plain bullets. Same four
  sections, same control, same nine authorization endings, same sixteen cuts;
  the sensitivity material and the Islamic-window note folded into single
  lines. Re-rendered to `docs/architecture.pdf`.
