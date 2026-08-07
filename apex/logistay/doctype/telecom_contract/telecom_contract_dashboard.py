# Copyright (c) 2026, afmcoltd
"""Form "Connections" for Telecom Contract: the SIM Cards it governs."""

from frappe import _


def get_data():
    """Lists SIM Card as the Telecom Contract form's connection."""
    return {
        "fieldname": "telecom_contract",
        "transactions": [
            {"label": _("SIMs"), "items": ["SIM Card"]},
        ],
    }
