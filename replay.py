#!/usr/bin/env python3
"""Replay the assignment's event stream and print the per-day report.

    python3 replay.py

Prints, for each of Days 1-6: events processed, any history restated by
backdated entries, overdraft fee assessments, closing ledger balances (plus
available balance where holds exist), authorization states and errors; on
Day 6 also the interest accrual schedule and the capitalised credit.
"""
from ledger.engine import Engine
from ledger.ledger import Ledger
from ledger.report import render_day, render_summary
from ledger.scenario import ACCOUNTS, EVENTS, WINDOW_DAYS


def main() -> None:
    engine = Engine(Ledger(ACCOUNTS), EVENTS, WINDOW_DAYS)
    for report in engine.run():
        print(render_day(report, engine.ledger))
        print()
    print(render_summary(engine))


if __name__ == "__main__":
    main()
