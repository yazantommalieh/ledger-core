"""Plain-text rendering of DayReports. No logic lives here."""
from __future__ import annotations

from .engine import DayReport, Engine
from .ledger import Kind, Ledger
from .money import PRECISION, fmt


def render_day(r: DayReport, ledger: Ledger) -> str:
    out = [f"=== Day {r.day} " + "=" * 56]
    out.append("Events")
    out.extend(f"  {line}" for line in r.processed) if r.processed else out.append("  (none)")

    if r.restated:
        out.append("History restated by today's postings (value-dated balances, before -> after)")
        for acct, days in r.restated.items():
            ccy = ledger.currency(acct)
            for k, (b, a) in sorted(days.items()):
                out.append(f"  {acct} Day {k}: {fmt(b, ccy)} -> {fmt(a, ccy)}")

    out.append("Overdraft fee assessments (in this close)")
    if r.fees:
        for f in r.fees:
            out.append(f"  {f.account} {fmt(f.amount, f.currency)} for Day {f.value_date} "
                       f"(value_date Day {f.value_date}, posted Day {f.posting_day})")
    else:
        out.append("  (none)")

    if r.interest_schedule:
        out.append("Interest — final daily accrual schedule (0.04%/day on positive closing balances)")
        for acct, sched in r.interest_schedule.items():
            ccy = ledger.currency(acct)
            cells = ", ".join(f"D{k}: {bal:,.{PRECISION[ccy]}f} -> {acc}" for k, (bal, acc) in sched.items())
            out.append(f"  {acct}: {cells}")
        for e in r.interest:
            out.append(f"  {e.account} capitalised {fmt(e.amount, e.currency)} (value_date Day {e.value_date})")
        if not r.interest:
            out.append("  (nothing to capitalise)")

    out.append("Closing ledger balance (entries with value_date <= today, as known today)")
    for acct, bal in r.closing.items():
        ccy = ledger.currency(acct)
        extra = ""
        if r.available[acct] != bal:
            extra = f"   available {fmt(r.available[acct], ccy)} (holds {fmt(bal - r.available[acct], ccy)})"
        acc = r.accrued_to_date.get(acct)
        prov = f"   interest accrued to date {fmt(acc, ccy)} (provisional)" if acc is not None and not r.interest_schedule else ""
        out.append(f"  {acct}: {fmt(bal, ccy)}{extra}{prov}")

    out.append("Authorization states")
    if r.auth_states:
        for auth_id, state in r.auth_states.items():
            a = ledger.auth(auth_id)
            detail = f"hold {fmt(a.amount, a.currency)} on {a.account}"
            if state == "SETTLED":
                s = ledger.settlement_of(auth_id)
                detail += f", settled {fmt(-s.amount, s.currency)} on Day {s.posting_day}"
            elif state == "DECLINED":
                detail += f", declined Day {a.posting_day} (available {a.available_before} -> {a.available_after})"
            elif state == "ACTIVE" and r.day == 6:
                detail += ", UNSETTLED at window end"
            out.append(f"  {auth_id}: {state} ({detail})")
    else:
        out.append("  (none)")

    out.append("Errors / warnings")
    if r.errors:
        for e in r.errors:
            out.append(f"  [{e.severity.value.upper()}] {e.event_id} {e.code}: {e.message}")
    else:
        out.append("  (none)")
    return "\n".join(out)


def render_summary(engine: Engine) -> str:
    lg = engine.ledger
    out = ["=== Window summary " + "=" * 50]
    for acct, ccy in lg.accounts.items():
        out.append(f"{acct} ({ccy})")
        out.append("  restated closing balances by value date: " +
                   ", ".join(f"D{k} {lg.balance(acct, k):,.{PRECISION[ccy]}f}"
                             for k in range(1, engine.window_days + 1)))
        fees = lg.entries_of_kind(Kind.FEE, acct)
        out.append(f"  overdraft fees: {len(fees)}" +
                   (" (" + ", ".join(f"Day {f.value_date}" for f in fees) + ")" if fees else ""))
        interest = lg.entries_of_kind(Kind.INTEREST, acct)
        out.append("  interest capitalised: " + (fmt(interest[0].amount, ccy) if interest else "none"))
        out.append(f"  final ledger balance: {fmt(lg.balance(acct, engine.window_days), ccy)}")
    out.append(f"Ledger entries: {len(lg.entries)}  auth records: {len(lg.auths)}  error records: {len(lg.errors)}")
    out.append("Append-only: every record above is still in the log; nothing was edited or removed.")
    return "\n".join(out)
