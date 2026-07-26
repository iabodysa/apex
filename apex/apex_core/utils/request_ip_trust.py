# Copyright (c) 2026, AFMCO and contributors
"""The trust boundary under every per-address limit in this app, made checkable (A-242).

``frappe.local.request_ip`` is the bucket key for the portal bad-token throttle
(portal_token_security), the boarding scan limiter (salis/api/boarding.py) and frappe's
own ``@rate_limit(ip_based=True)``. frappe fills it from the FIRST ``X-Forwarded-For``
entry with no trusted-proxy check at all::

    def set_request_ip(self):
        if frappe.get_request_header("X-Forwarded-For"):
            frappe.local.request_ip = (frappe.get_request_header("X-Forwarded-For").split(",", 1)[0]).strip()
        elif frappe.get_request_header("REMOTE_ADDR"):
            frappe.local.request_ip = frappe.get_request_header("REMOTE_ADDR")
        ...
    -- frappe/auth.py:64-75 (v15.109.0)

Nothing in that chain asks who set the header. A caller that forges a fresh value per
request lands in a fresh window every time and walks through all three limiters, and can
equally pin the blame for a flood on any address it names. The safety is entirely
deployment-side: the reverse proxy must OVERWRITE the header with the real peer, never
append the client's claim to it.

frappe's only ``ProxyFix`` (app.py:500) does NOT close this. It is bound to ``serve()``,
the dev server, behind an opt-in ``proxy``/``USE_PROXY`` flag, so no production WSGI path
receives it -- and even where it runs it is dead for this purpose, because it rewrites
``request.remote_addr`` while ``set_request_ip`` reads the raw header first and never
reaches the ``remote_addr`` branch beneath it. There is no trusted-proxy setting to set.

So the requirement cannot be enforced from inside the app; it can only be MEASURED
against a running deployment. That is what this module is: a deterministic verdict a
deployer gets from one authenticated request, not a warning in a log nobody opens.

The probe is what makes it decisive, and it takes TWO channels to work. The deployer
sends a documentation-range address (RFC 5737 / RFC 3849) in ``X-Forwarded-For`` -- a
value no real client can ever legitimately carry -- and separately asserts having done
so in the QUERY STRING, which a reverse proxy forwards verbatim. The header alone cannot
carry that news: a correctly configured edge ERASES it, so its absence would be read as
"no probe sent" and the passing deployment would grade itself INCONCLUSIVE. Two channels
turn silence into the signal: the probe was sent, it did not arrive, therefore the edge
overwrote it. Without the assertion, one header entry is genuinely inconclusive -- an
overwriting proxy and a wide-open direct exposure produce the identical shape.
"""

from __future__ import annotations

import ipaddress

import frappe
from frappe.utils import cint

FORWARDED_HEADER = "X-Forwarded-For"

# The address the runbook names, so both sides of the check quote one string. Any
# documentation-range value works; this one is only the default the instructions use.
PROBE_ADDRESS = "192.0.2.7"

# Reserved for documentation and examples, so routable traffic never legitimately
# carries one -- RFC 5737 (IPv4) and RFC 3849 (IPv6).
_DOCUMENTATION_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32")
)

# The probe was sent and did not survive: the edge replaced it with the real peer.
OVERWRITTEN = "overwritten"
# The probe was sent and came back as the client address: the header is trusted whole.
FORGEABLE = "forgeable"
# Two or more entries, so the edge appended the client's claim instead of replacing it.
# frappe reads the first entry, which is the one the client chose.
APPENDED = "appended"
# No header reached the app at all.
NO_HEADER = "no-header"
# One entry and no probe asserted: an overwriting edge and a direct exposure match here.
INCONCLUSIVE = "inconclusive"

_DETAIL = {
    OVERWRITTEN: (
        "PASS. The probe was sent and the server did not resolve it, so the edge "
        f"overwrites {FORWARDED_HEADER} with the real peer. Per-address limits key "
        "on a value the caller cannot choose."
    ),
    FORGEABLE: (
        "FAIL. The server resolved the documentation-range probe as the client "
        f"address, so {FORWARDED_HEADER} is trusted verbatim. Every per-address "
        "limit in this app is bypassed by varying that header, and any address can "
        "be framed for another caller's traffic."
    ),
    APPENDED: (
        f"FAIL. {FORWARDED_HEADER} carries more than one entry, so the edge appends "
        "the client's claim rather than replacing it. frappe reads the FIRST entry "
        "(auth.py:65-66), which is the client's, so per-address limits key on a "
        "value the caller chooses."
    ),
    NO_HEADER: (
        f"INCOMPLETE. No {FORWARDED_HEADER} reached the app. If nothing proxies this "
        "site the peer is genuine; if a proxy is in front and simply does not set the "
        "header, every client collapses onto its address and one abuser can 429 all "
        "of them."
    ),
    INCONCLUSIVE: (
        f"INCONCLUSIVE. One {FORWARDED_HEADER} entry and no probe asserted: an "
        "overwriting proxy and a directly exposed app are indistinguishable in this "
        f"shape. Re-send with header {FORWARDED_HEADER}: {PROBE_ADDRESS} and query "
        "parameter probe_planted=1."
    ),
}


def forwarded_entries(raw: str | None) -> list[str]:
    """The header split the way an appending proxy builds it: client claim first."""
    return [entry.strip() for entry in (raw or "").split(",") if entry.strip()]


def is_documentation_address(value: str | None) -> bool:
    """Whether a value is reserved for documentation, so no real client can carry it."""
    try:
        address = ipaddress.ip_address((value or "").strip())
    except ValueError:
        return False
    return any(address in network for network in _DOCUMENTATION_NETWORKS)


def classify_forwarding(
    raw: str | None,
    resolved_ip: str | None,
    probe_planted: bool = False,
) -> dict:
    """Grade one observed request against the trust boundary.

    ``resolved_ip`` is what frappe actually put in ``request_ip`` -- read, never
    recomputed here, so this cannot drift from ``auth.py``'s precedence and pass a
    deployment on a rule the framework has stopped following.

    A surviving probe is graded FIRST because it is the only positive proof that the
    resolved address was attacker-chosen. A multi-entry header is graded next and
    regardless of the probe, so a stray shape is never absolved by a passing probe.
    """
    entries = forwarded_entries(raw)
    probe_seen = any(is_documentation_address(entry) for entry in entries)

    if probe_planted and is_documentation_address(resolved_ip):
        verdict = FORGEABLE
    elif len(entries) > 1:
        verdict = APPENDED
    elif probe_planted:
        verdict = OVERWRITTEN
    elif entries:
        verdict = INCONCLUSIVE
    else:
        verdict = NO_HEADER

    return {
        "verdict": verdict,
        "trusted": verdict == OVERWRITTEN,
        "forgeable": verdict in (FORGEABLE, APPENDED),
        "probe_planted": bool(probe_planted),
        "probe_seen": probe_seen,
        "entries": entries,
        "resolved_ip": resolved_ip,
        "detail": _DETAIL[verdict],
    }


@frappe.whitelist()
def check_request_ip_trust(probe_planted=None) -> dict:
    """Report whether this deployment's edge lets a caller choose its own address.

    Read-only and System Manager only: the reply names the address the server believes
    the caller has, which is the fact an attacker probing the edge is after.

    ``probe_planted`` is the caller's assertion that this same request carried a
    documentation-range ``X-Forwarded-For``. It rides the query string because the edge
    under test is expected to destroy the header, and a passing deployment must not be
    graded inconclusive for having done exactly what it should.

        curl -s --cookie sid=<system-manager-sid> \\
             -H 'X-Forwarded-For: 192.0.2.7' \\
             'https://<site>/api/method/apex.apex_core.utils.request_ip_trust.check_request_ip_trust?probe_planted=1'

    ``verdict: overwritten`` is the only pass.
    """
    frappe.only_for("System Manager")
    return classify_forwarding(
        frappe.get_request_header(FORWARDED_HEADER),
        getattr(frappe.local, "request_ip", None),
        probe_planted=bool(cint(probe_planted)),
    )
