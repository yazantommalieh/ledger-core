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
