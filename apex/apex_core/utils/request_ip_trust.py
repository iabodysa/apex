# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import ipaddress

import frappe
from frappe.utils import cint

FORWARDED_HEADER = "X-Forwarded-For"

PROBE_ADDRESS = "192.0.2.7"

_DOCUMENTATION_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32")
)

OVERWRITTEN = "overwritten"
OVERWRITTEN_THEN_APPENDED = "overwritten-then-appended"
FORGEABLE = "forgeable"
APPENDED = "appended"
NO_HEADER = "no-header"
INCONCLUSIVE = "inconclusive"

PASSING_VERDICTS = (OVERWRITTEN, OVERWRITTEN_THEN_APPENDED)
FAILING_VERDICTS = (FORGEABLE, APPENDED)

_DETAIL = {
    OVERWRITTEN: (
        "PASS, resting on your assertion that this request carried a "
        f"documentation-range {FORWARDED_HEADER}. No such entry arrived, so the edge "
        "overwrites the header with the real peer and per-address limits key on a "
        "value the caller cannot choose. The verdict is VOID if the request did not "
        "in fact carry the probe: a destroyed header is exactly what the server "
        "cannot see, so the assertion is taken on trust and never verified."
    ),
    OVERWRITTEN_THEN_APPENDED: (
        "PASS, resting on your assertion that this request carried a "
        f"documentation-range {FORWARDED_HEADER}. No entry carries it, so the hop "
        "facing the caller REPLACED the header and the later entries were appended "
        "behind that replacement by hops further in. frappe reads the FIRST entry "
        "(auth.py:66), which is the replacement. Same caveat: the assertion is taken "
        "on trust. Confirm every later entry is a hop you operate, because putting an "
        "APPENDING hop in front of the replacing one turns this forgeable."
    ),
    FORGEABLE: (
        "FAIL. The documentation-range probe survived the edge, so "
        f"{FORWARDED_HEADER} is trusted verbatim. Every per-address limit in this app "
        "is bypassed by varying that header, and any address can be framed for "
        "another caller's traffic."
    ),
    APPENDED: (
        f"FAIL. {FORWARDED_HEADER} carries more than one entry and no probe was "
        "asserted, so nothing shows whether the first entry is the caller's claim or "
        "a replacement. frappe reads the FIRST entry (auth.py:66), so treat it as "
        f"caller-chosen until a probe proves otherwise: re-send with header "
        f"{FORWARDED_HEADER}: {PROBE_ADDRESS} and query parameter probe_planted=1."
    ),
    NO_HEADER: (
        f"INCOMPLETE. No {FORWARDED_HEADER} reached the app, so the edge's overwrite "
        "behaviour was not measured. This is NOT a pass, and a planted probe that was "
        "destroyed outright does not make it one. If nothing proxies this site the "
        "peer is genuine; if a proxy is in front and simply does not set the header, "
        "every client collapses onto its address and one abuser can 429 all of them."
    ),
    INCONCLUSIVE: (
        f"INCONCLUSIVE. Either one {FORWARDED_HEADER} entry and no probe asserted, a "
        "shape an overwriting proxy and a directly exposed app both produce; or the "
        f"resolved address is not the first {FORWARDED_HEADER} entry, so something "
        "other than auth.py:66 chose it and this check cannot reason about it. "
        f"Compare entries against resolved_ip, then re-send with header "
        f"{FORWARDED_HEADER}: {PROBE_ADDRESS} and query parameter probe_planted=1."
    ),
}


def forwarded_entries(raw: str | None) -> list[str]:
    return [entry.strip() for entry in (raw or "").split(",") if entry.strip()]


def _bare_address(value: str | None) -> ipaddress._BaseAddress | None:
    text = (value or "").strip()
    if text.startswith("["):
        text = text[1:].split("]", 1)[0]
    elif text.count(":") == 1:
        text = text.split(":", 1)[0]
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return None
    return getattr(address, "ipv4_mapped", None) or address


def is_documentation_address(value: str | None) -> bool:
    address = _bare_address(value)
    if address is None:
        return False
    return any(address in network for network in _DOCUMENTATION_NETWORKS)


def classify_forwarding(
    raw: str | None,
    resolved_ip: str | None,
    probe_planted: bool = False,
) -> dict:
    entries = forwarded_entries(raw)
    probe_seen = any(is_documentation_address(entry) for entry in entries)
    reads_first_entry = bool(entries) and resolved_ip == entries[0]
    unreadable = [entry for entry in entries if _bare_address(entry) is None]

    if not entries:
        verdict = NO_HEADER
    elif probe_planted and (probe_seen or is_documentation_address(resolved_ip)):
        verdict = FORGEABLE
    elif not probe_planted:
        verdict = APPENDED if len(entries) > 1 else INCONCLUSIVE
    elif unreadable:
        verdict = INCONCLUSIVE
    elif not reads_first_entry:
        verdict = INCONCLUSIVE
    elif len(entries) > 1:
        verdict = OVERWRITTEN_THEN_APPENDED
    else:
        verdict = OVERWRITTEN

    return {
        "verdict": verdict,
        "trusted": verdict in PASSING_VERDICTS,
        "forgeable": verdict in FAILING_VERDICTS,
        "probe_planted": bool(probe_planted),
        "probe_seen": probe_seen,
        "entries": entries,
        "resolved_ip": resolved_ip,
        "detail": _DETAIL[verdict],
    }


@frappe.whitelist()
def check_request_ip_trust(probe_planted=None) -> dict:
    frappe.only_for("System Manager")
    return classify_forwarding(
        frappe.get_request_header(FORWARDED_HEADER),
        getattr(frappe.local, "request_ip", None),
        probe_planted=bool(cint(probe_planted)),
    )
