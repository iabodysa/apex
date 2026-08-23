# Copyright (c) 2026, afmcoltd
"""Phone-number cleanup shared by the portal identity layer and the messaging gateway.

Portal Identity (kernel) resolves the stored phone a credential goes to;
the Salis messaging gateway sends to it. Both need the same light cleanup —
strip spaces/dashes/parens, keep a single leading ``+`` — before comparing or
dialling a number, with no provider-specific validation attempted here (the
gateway/provider does that). This absorbed what was a private helper on
``apex.salis.api.messaging_gateway`` that Portal Identity reached into through
a body-scoped import to break the cycle that created (the gateway itself
imports Portal Identity at module load); a second copy anywhere else is this
cleanup rule drifting between the two callers.
"""

from __future__ import annotations


def normalize_phone(phone) -> str | None:
    """Trim a phone to digits and a single leading ``+``, or None when empty."""
    phone = (phone or "").strip()
    if not phone:
        return None
    cleaned = "".join(ch for ch in phone if ch.isdigit())
    return ("+" + cleaned) if phone.startswith("+") else cleaned or None
