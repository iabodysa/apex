# Copyright (c) 2026, AFMCO and contributors
"""WPS SIF (Salary Information File) assembly for the Logistay payroll (P-192).

The regional wage-protection file is grouped PER ESTABLISHMENT (the MOL / labor-office
establishment the workers belong to). This module only groups the already-computed
Salary Slip nets and reconciles the totals; the actual file bytes are produced by the
chosen export channel (D10 procurement), never here.

The single invariant enforced: for every establishment, the SIF total equals the exact
sum of the underlying Salary Slip nets, and the grand total equals the sum of all slip
nets. Currency is rounded to 2 decimals so the reconciliation is bit-stable.
"""

from __future__ import annotations

from frappe.utils import flt


def build_wps_sif(slips):
    """Group Salary Slips into per-establishment SIF blocks whose totals tie to the slips.

    ``slips``: iterable of records each carrying ``establishment`` and ``net`` (a
    ``get_all`` result or list of dicts). Returns a deterministic structure::

        {
          "establishments": {
              <establishment>: {"record_count": int, "total_net": flt},
              ...
          },
          "grand_total_net": flt,
        }

    Establishments are keyed in sorted order so the emitted file is deterministic.
    """
    establishments: dict = {}
    for slip in slips:
        est = _get(slip, "establishment")
        net = flt(_get(slip, "net"), 2)
        block = establishments.setdefault(est, {"record_count": 0, "total_net": 0.0})
        block["record_count"] += 1
        block["total_net"] = flt(block["total_net"] + net, 2)

    ordered = {est: establishments[est] for est in sorted(establishments, key=lambda k: str(k))}
    grand_total = flt(sum(b["total_net"] for b in ordered.values()), 2)
    return {"establishments": ordered, "grand_total_net": grand_total}


def sif_reconciles(sif, slips) -> bool:
    """True iff every establishment's SIF total equals the summed slip nets for it,
    and the grand total equals the sum of all slip nets. Independent recomputation so
    a tampered total (or a dropped slip) makes this fail closed."""
    expected: dict = {}
    for slip in slips:
        est = _get(slip, "establishment")
        expected[est] = flt(expected.get(est, 0.0) + flt(_get(slip, "net"), 2), 2)

    emitted = sif.get("establishments", {})
    if set(emitted) != set(expected):
        return False
    for est, want in expected.items():
        if flt(emitted[est]["total_net"], 2) != flt(want, 2):
            return False
    return flt(sif.get("grand_total_net"), 2) == flt(sum(expected.values()), 2)


def _get(slip, key):
    """Read ``key`` off a dict-like or attr-like slip record."""
    if isinstance(slip, dict):
        return slip.get(key)
    return getattr(slip, key, None)
