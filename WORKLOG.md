# WORKLOG

All times are Asia/Dubai (UTC+4). Entries are appended as the work happens.
One later edit, on 5 Nov at 22:15: the Part 2 revision entries were folded into
one and conversational wording was removed; no times or facts changed. The
commit history is the other half of this log.

**Tooling disclosure:** this repository was built in a single working session
using Claude (Anthropic) as a pair-programmer, as the assignment permits.
Yazan supplied the assignment, asked for a walkthrough of the problem, agreed
the approach, and reviewed the results; Claude wrote the code and the first
draft of every document in this repo. The first section below is Yazan's own
log, in his words. The second is the build log Claude appended as the work
happened. Entries say who did what.

---

## Yazan's log

### 4 November

- **11:20** — Read the core ledger assignment, structured it for my brain to
  understand it.
- **11:35** — Asked the AI to explain the task in a more structured way so I
  could validate my initial understanding.
- **11:45** — Asked the AI to create a base version to build on. Used the best
  model available (Claude, max reasoning effort) since this is a critical
  payments system.
- **11:50** — AFK, letting Claude do its work; it will take a while.
- **12:26** — Claude finished the initial build. AFK again for personal
  reasons, will come back to it later.
- **15:30** — Reviewing the AI base solution. Moved the repo to my Mac and
  re-authored the commits with my own email.
- **16:30** — Started to manually re-evaluate the stream and produce my own
  results to compare against the AI's.
- **16:48** — AFK.
- **17:38** — Continued the manual evaluation.
- **18:40** — Manual evaluation by calculation complete. My first pass missed
  the Day 5 fee and modelled the Auth-A hold as a −200 debit instead of a
  hold; after correcting those two, my numbers and the AI's matched.
- **18:41** — AFK.

### 5 November

- **16:00** — Checked and validated the provided criteria, to decide which
  are wrong and why. Done.
- **16:28** — Asked for a full re-evaluation of the solution at maximum
  reasoning effort. Numbers and verdicts unchanged; three input-validation
  gaps found and fixed.
- **16:44** — Shared the Part 2 brief (architecture and trade-offs document)
  and asked for a first draft. AFK after it landed.
- **21:10** — Reviewed the architecture document and iterated on length,
  structure and wording until it fit two pages, matched the brief's scope and
  read in my own voice.
- **22:00** — Architecture and trade-offs document completed.
- **22:00** — Manually running the automated tests, getting ready to submit.
  78 green, the known-limitation test red as intended, replay matches.

---

## Build log (Claude)

Short entries. The reasoning behind each decision is in AMBIGUITIES.md,
REJECTED.md and NUMBERS.md; this is only what happened and when.

### 4 November

- **11:26** — Assignment read. Key observation: two clocks (posting day vs
  value date), E7 and E9 are backdated, four of the eight criteria are wrong.
- **11:43** — Plan: Python 3 with `decimal`, stdlib `unittest`, one package
  `ledger/`, a `replay.py` runner, one commit per stage, docs written
  alongside the code.
- **11:46** — Repo scaffolded.
- **11:47** — `money.py`: Decimal only, HALF_UP, hard precision table,
  instalment split with the remainder on the last part. 12 tests. (This entry
  was first stamped 11:52 by hand; the commit time is used here. See 12:25.)
- **11:49** — `events.py` and `ledger.py`: append-only store;
  `balance(account, value_date_upto, as_of_posting_day)` is the one
  primitive; hold state derived; no running balance. 27 tests.
- **11:50** — Engine v1 (commit `91a5570`): fee check on the current day only,
  accruals stored per day. Wrong: one fee instead of three, interest 0.83.
  Kept in history as an abandoned approach.
- **11:51** — Engine v2 (`98f7a67`): fees re-assessed for every past day at
  each close. Fees for Days 2, 4, 5. Interest still from stored snapshots
  (0.81).
- **11:51** — Engine v3 (`e2b74ec`): interest schedule derived from the
  restated history. Finals 390.93 and 10.008.
- **11:52** — `report.py` and `replay.py`: per-day printout with a "history
  restated" block.
- **11:54** — Tests: one class per criterion plus edge cases. Two of my own
  assertions were wrong (a 3-day window capitalises on Day 3); fixed the
  tests, not the engine. 67 green.
- **11:54** — The failing test, `known_limitation_test.py`: fees do not
  unwind when E7 is reversed. Makefile added.
- **11:58** — README, NUMBERS.md (half and double figures verified by running
  the engine), AMBIGUITIES.md (23 items), REJECTED.md.
- **12:25** — Independent review by a second agent that had not seen the
  build. Its hand calculation matched the program. Found and fixed (commit
  `0bbc4b9`): credits bypassed the precision check; the unconfigured-fee error
  repeated at every close; capitalisation was not idempotent; reversals
  ignored their account field; a hard-coded day 6 in the report. Doc
  corrections: v1 interest was 0.83 not 0.81; the AED-at-1dp claim in
  NUMBERS.md; the failing test's annotated figure 465.93 → 466.03; criterion
  6 reworded from "impossible" to "not implemented, needs an unstated rule".
  Six ambiguities added (§24–29). Also caught the hand-typed 11:52 stamp
  above; every later stamp comes from the clock. 75 tests.
- **15:42** — Repo moved to Yazan's Mac. Commits re-authored with his email
  (email only; messages, diffs and times unchanged). Hash references in the
  docs updated to match.

### 5 November

- **16:34** — Full re-evaluation: six days recomputed by hand, every
  criterion and ambiguity re-argued from the spec text. Numbers and verdicts
  unchanged. Fixed three input gaps (settlement on the wrong account,
  non-positive amounts, duplicate event ids). 78 tests. Strengthened §2, §3,
  §6 and §12; added §30–31 and a "what each choice is worth" table (final
  balance under each rejected reading: 390.97 / 390.81 / 440.83 / 210.69 /
  466.03, against 390.93).
- **16:52** — Part 2 drafted from the implementation. Regulatory references
  looked up, not recalled; the AML law had been replaced by Federal
  Decree-Law No. 10 of 2025, so that is the one cited. 4 pages.
- **21:24–21:43** — Part 2 revised in four commits: plain bullets; styling
  and grouped tables; two pages; a scope pass (endings in the model vs. not,
  one control, UAE only) and plain first-person wording. Final: 2 pages,
  about 1,520 words. `docs/render.js` renders the PDF.
