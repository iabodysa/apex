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

Silence in the HEADER is the pass signal; silence on the WIRE is not. A request that
reaches the app carrying no forwarded header at all measured nothing about overwriting,
so it is graded incomplete even when a probe was planted and destroyed: the deployment
where the edge strips the header and sets nothing keys every client onto the proxy's own
address, which is a different failure, not a pass.
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
# The probe was sent, no entry carries it, and entries remain: the caller-facing hop
# replaced the header and inner hops appended behind that replacement.
OVERWRITTEN_THEN_APPENDED = "overwritten-then-appended"
# The probe was sent and survived anywhere in the header: caller content reaches the app.
FORGEABLE = "forgeable"
# Two or more entries and no probe to tell which hop wrote the first one.
APPENDED = "appended"
# No header reached the app at all, so the edge's overwrite behaviour went unmeasured.
NO_HEADER = "no-header"
# Nothing separates an overwriting edge from a direct exposure in the observed shape.
INCONCLUSIVE = "inconclusive"

# Verdicts under which request_ip is not caller-choosable. Frozen vocabulary: the
# deployer runbook quotes these strings, so a rename is a documentation change.
PASSING_VERDICTS = (OVERWRITTEN, OVERWRITTEN_THEN_APPENDED)
FAILING_VERDICTS = (FORGEABLE, APPENDED)

_DETAIL = {
    OVERWRITTEN: (
        "PASS. The probe was sent and the server did not resolve it, so the edge "
        f"overwrites {FORWARDED_HEADER} with the real peer. Per-address limits key "
        "on a value the caller cannot choose."
    ),
    OVERWRITTEN_THEN_APPENDED: (
        f"PASS. The probe was sent and no {FORWARDED_HEADER} entry carries it, so the "
        "hop facing the caller REPLACED the header; the later entries were appended "
        "behind that replacement by hops further in. frappe reads the FIRST entry "
        "(auth.py:66), which is the replacement, so per-address limits key on a value "
        "the caller cannot choose. Confirm every later entry is a hop you operate: "
        "putting an APPENDING hop in front of the replacing one turns this forgeable."
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

    The discriminator is the probe's ABSENCE, and it is exact. Every appending edge
    appends to the TAIL (``$proxy_add_x_forwarded_for`` is ``$http_x_forwarded_for,
    $remote_addr``), so a claim the caller sent can only ever sit at the HEAD, which is
    the one entry frappe reads. Therefore, once the caller asserts a probe was planted,
    the probe missing from every entry means the hop facing the caller replaced the
    header, and entry COUNT no longer bears on safety: a replacement with appends behind
    it is as safe as a lone replacement. The probe present anywhere means the opposite,
    whatever address frappe happened to resolve.

    Three shapes must never reach a passing verdict, and each is graded before the
    passes: no header at all, because an erased header measures nothing about
    overwriting; a surviving probe, because caller content demonstrably reaches the app;
    and a resolved address that is not the first entry, because the reasoning above is
    then about a precedence the framework is not following.
    """
    entries = forwarded_entries(raw)
    probe_seen = any(is_documentation_address(entry) for entry in entries)
    reads_first_entry = bool(entries) and resolved_ip == entries[0]

    if not entries:
        verdict = NO_HEADER
    elif probe_planted and (probe_seen or is_documentation_address(resolved_ip)):
        verdict = FORGEABLE
    elif not probe_planted:
        verdict = APPENDED if len(entries) > 1 else INCONCLUSIVE
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

    ``overwritten`` and ``overwritten-then-appended`` are the passes; both are also
    reported as ``trusted: true``, which is the field to key an automated check on.
    Every other verdict, ``no-header`` included, is a refusal to certify.
    """
    frappe.only_for("System Manager")
    return classify_forwarding(
        frappe.get_request_header(FORWARDED_HEADER),
        getattr(frappe.local, "request_ip", None),
        probe_planted=bool(cint(probe_planted)),
    )
