# Copyright (c) 2026, AFMCO and contributors
"""Generic per-day-rate resolver (P-189 / A-019).

Turns a Rate Card's seeded component value into the per-day rate ACTUALLY
applied, per the line's day-rate BASIS (C3). The divisor is DERIVED from the
basis + the worker-month context — never a hardcoded AFMCO money value:

    explicit_rate_per_day  divisor 1        the value IS already the day rate
    div_31                 divisor 31       fixed 31-day-month convention
    fixed_365_12           divisor 365/12   fixed average-month convention
    actual_cycle_days      divisor N        N = the worker-month's own day count

    day_rate = round(component_value / divisor, 2)

The only per-basis constants here are CALENDAR conventions encoded by the basis
enum itself (31, 365/12); the ``actual_cycle_days`` divisor is DATA supplied by
the worker-month at resolve time, and ``explicit_rate_per_day`` reads the seeded
value straight through. No AFMCO rate / client / amount value lives in this
module — only the enum domain imported from ``reconciliation_engine``.

Both output sides consume this ONE function, so the Billable Line and the
Payable Line derived from the same resolution snapshot the IDENTICAL basis (the
pairing key the P-190 BASIS-CONSISTENT guard later compares).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from apex.logistay.reconciliation_engine import DAY_RATE_BASIS

# Currency day rate rounds to cents.
_CENTS = Decimal("0.01")

# Divisor CONVENTION per fixed basis — calendar constants named by the basis
# enum, not AFMCO values. ``actual_cycle_days`` is deliberately absent: its
# divisor is DATA (the worker-month day count), supplied at resolve time.
_FIXED_DIVISORS: dict[str, Decimal] = {
    "explicit_rate_per_day": Decimal(1),
    "div_31": Decimal(31),
    "fixed_365_12": Decimal(365) / Decimal(12),
}


def divisor_for_basis(basis: str, cycle_days: int | None = None) -> Decimal:
    """The per-day divisor for ``basis``.

    ``actual_cycle_days`` reads the worker-month's own day count (data); every
    other basis is a fixed calendar convention. Raises on an unknown basis or a
    missing/invalid cycle length so a misconfigured card fails loud, never
    silently misprices.
    """
    if basis not in DAY_RATE_BASIS:
        raise ValueError(f"Unknown day-rate basis: {basis!r}")
    if basis == "actual_cycle_days":
        if not cycle_days or int(cycle_days) <= 0:
            raise ValueError(
                "actual_cycle_days basis needs a positive worker-month cycle_days"
            )
        return Decimal(int(cycle_days))
    return _FIXED_DIVISORS[basis]


def resolve_day_rate(
    component_value, basis: str, cycle_days: int | None = None
) -> Decimal:
    """Per-day rate for one seeded component value under one basis, in cents.

    ``component_value`` is the seeded Rate Card value — a period/monthly package
    for the divisor bases, or already a day rate for ``explicit_rate_per_day``.
    Decimal-exact and deterministic: identical inputs always yield identical
    output.
    """
    value = Decimal(str(component_value))
    divisor = divisor_for_basis(basis, cycle_days)
    return (value / divisor).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _day_rate_row(card):
    """The single ``day_rate`` component line on a Rate Card (doc or dict-like)."""
    rows = getattr(card, "rc_components", None)
    if rows is None and isinstance(card, dict):
        rows = card.get("rc_components")
    for row in rows or []:
        component = getattr(row, "rc_component", None)
        if component is None and isinstance(row, dict):
            component = row.get("rc_component")
        if component == "day_rate":
            return row
    return None


def resolve_from_card(card, cycle_days: int | None = None) -> dict:
    """Resolve a Rate Card's day-rate line into the snapshot destined for BOTH
    output lines.

    ``card`` is a Rate Card document (any object exposing ``rc_components`` rows
    with ``rc_component`` / ``rc_value`` / ``rc_day_rate_basis``). Returns the
    two snapshot fields that both the Billable Line and the Payable Line copy
    verbatim, so their bases can never diverge:

        {"rc_day_rate_applied": Decimal, "rc_day_rate_basis_applied": basis}
    """
    row = _day_rate_row(card)
    if row is None:
        raise ValueError("Rate Card has no day_rate component line to resolve")
    basis = getattr(row, "rc_day_rate_basis", None)
    if basis is None and isinstance(row, dict):
        basis = row.get("rc_day_rate_basis")
    if not basis:
        raise ValueError("day_rate line has no day-rate basis to resolve against")
    value = getattr(row, "rc_value", None)
    if value is None and isinstance(row, dict):
        value = row.get("rc_value")
    return {
        "rc_day_rate_applied": resolve_day_rate(value, basis, cycle_days),
        "rc_day_rate_basis_applied": basis,
    }
