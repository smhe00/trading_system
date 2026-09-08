"""Pure point-in-time (PIT) fundamental helpers for the Midea data audit.

These implement the fail-closed availability rules independently of any live
data source, so the audit logic is deterministic and testable:

- a financial record activates for trading date ``t`` ONLY via an historical
  availability/disclosure timestamp — NEVER via report period alone;
- a same-day disclosure with unknown time-of-day becomes usable from the NEXT
  trading day (conservative policy);
- a missing availability timestamp fails closed (record is never usable);
- candidate-feature feasibility is classified strictly from the set of
  fields that are actually available with PIT-safe lineage.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

# Feature feasibility labels (task §9).
DIRECTLY_AVAILABLE = "DIRECTLY_AVAILABLE"
DERIVABLE_PIT_SAFE = "DERIVABLE_PIT_SAFE"
DERIVABLE_BUT_MISSING_REQUIRED_HISTORY = "DERIVABLE_BUT_MISSING_REQUIRED_HISTORY"
PIT_UNSAFE = "PIT_UNSAFE"
UNAVAILABLE = "UNAVAILABLE"


def first_usable_trading_date(
    disclosure_date: Optional[date],
    trading_dates,
    policy: str = "next_trading_day",
) -> Optional[date]:
    """First trading date on which a record with ``disclosure_date`` is usable.

    ``policy="next_trading_day"`` (default): disclosure with unknown time of
    day becomes usable only from the NEXT trading day (strictly after the
    disclosure date). ``policy="same_day"``: usable from the first trading
    day on or after the disclosure date. Returns None when no such date
    exists or when the disclosure date is missing (fail closed).
    """
    if disclosure_date is None:
        return None
    for d in trading_dates:
        if policy == "next_trading_day":
            if d > disclosure_date:
                return d
        else:
            if d >= disclosure_date:
                return d
    return None


def build_as_of_panel(
    records: list,
    trading_dates,
    disclosure_key: str = "disclosure_date",
    record_key: str = "record",
    policy: str = "next_trading_day",
) -> list:
    """Minimal as-of proof panel: for each trading date ``t`` return the
    records whose disclosure date makes them usable by ``t``.

    ``records`` is a list of dicts each with ``disclosure_date`` (a ``date``
    or None) and ``record`` (any payload). A record with a missing disclosure
    date is never selected (fail closed). No transformation/optimization.
    """
    usable = {}
    for rec in records:
        first = first_usable_trading_date(rec.get(disclosure_key), trading_dates, policy)
        if first is None:
            continue
        usable.setdefault(first, []).append(rec[record_key])
    panel = []
    active = []
    for d in trading_dates:
        active.extend(usable.get(d, []))
        panel.append({"trading_date": d, "active_records": list(active)})
    return panel


def classify_feature(
    required_fields: list,
    available_pit_safe_fields: set,
    derivable_from: Optional[dict] = None,
    history_complete: bool = True,
) -> str:
    """Feasibility classification of a candidate feature (task §9).

    ``required_fields`` are the raw PIT-safe concepts the feature needs;
    ``available_pit_safe_fields`` is the audited set of raw fields that are
    actually available with PIT-safe lineage; ``derivable_from`` optionally
    maps a missing concept to the list of available fields it could be
    derived from. Purely descriptive: correctness and lineage are the gate.
    """
    required = set(required_fields)
    missing = [f for f in required if f not in available_pit_safe_fields]
    if not missing:
        return DIRECTLY_AVAILABLE
    derivable = derivable_from or {}
    if all(
        f in derivable
        and set(derivable[f]).issubset(available_pit_safe_fields)
        for f in missing
    ):
        return DERIVABLE_PIT_SAFE if history_complete else DERIVABLE_BUT_MISSING_REQUIRED_HISTORY
    if any(f in available_pit_safe_fields for f in required):
        return DERIVABLE_BUT_MISSING_REQUIRED_HISTORY
    return UNAVAILABLE
