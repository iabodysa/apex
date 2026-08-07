# Copyright (c) 2026, afmcoltd
"""Normalization helpers for SIM identifiers.

The mobile number stays editable in place on SIM Card, so its uniqueness cannot
be enforced on the raw human-entered string ("055 123 4567" vs "+966551234567"
must collide). Each SIM Card stores a derived, read-only normalized key that the
uniqueness guard compares — never the display value. ICCID follows the same
rule when present. The normalized forms live ONCE here so the controller, the
migration patch, and any importer share one definition and cannot drift.
"""

from __future__ import annotations

import re

_MSISDN_STRIP = re.compile(r"[^\d+]")
_NON_ALNUM = re.compile(r"[^0-9A-Za-z]")


def normalize_msisdn(value: str | None) -> str | None:
    """Return the comparison key for a mobile number, or None when empty.

    Strips spaces, dashes, dots and parentheses, keeps a single leading ``+``
    country prefix, and drops any other stray ``+``. The result is a
    digits(+prefix) string used only as the uniqueness key; the SIM Card keeps
    the operator's original text in ``mobile_number`` for display and editing.
    """
    if value is None:
        return None
    cleaned = _MSISDN_STRIP.sub("", str(value)).strip()
    if not cleaned:
        return None
    has_prefix = cleaned.startswith("+")
    digits = cleaned.replace("+", "")
    if not digits:
        return None
    return ("+" + digits) if has_prefix else digits


def normalize_iccid(value: str | None) -> str | None:
    """Return the comparison key for an ICCID, or None when empty.

    ICCID is an alphanumeric integrated-circuit id; strip separators and
    upper-case it so "8996 1100 0000 0000 001" and its spaced variants collide.
    Uniqueness is enforced only when a value is present (ICCID is optional).
    """
    if value is None:
        return None
    cleaned = _NON_ALNUM.sub("", str(value)).upper().strip()
    return cleaned or None
