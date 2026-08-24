# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import re

_MSISDN_STRIP = re.compile(r"[^\d+]")
_NON_ALNUM = re.compile(r"[^0-9A-Za-z]")


def normalize_msisdn(value: str | None) -> str | None:
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
    if value is None:
        return None
    cleaned = _NON_ALNUM.sub("", str(value)).upper().strip()
    return cleaned or None
