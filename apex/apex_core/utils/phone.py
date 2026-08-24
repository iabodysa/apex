# Copyright (c) 2026, afmcoltd

from __future__ import annotations


def normalize_phone(phone) -> str | None:
    phone = (phone or "").strip()
    if not phone:
        return None
    cleaned = "".join(ch for ch in phone if ch.isdigit())
    return ("+" + cleaned) if phone.startswith("+") else cleaned or None
