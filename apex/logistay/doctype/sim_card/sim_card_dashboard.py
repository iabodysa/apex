# Copyright (c) 2026, afmcoltd
"""Form "Connections" for SIM Card: its custody history."""

from frappe import _


def get_data():
    """Lists SIM Custody Assignment as the SIM Card form's custody connection."""
    return {
        "fieldname": "sim_card",
        "transactions": [
            {"label": _("Custody"), "items": ["SIM Custody Assignment"]},
        ],
    }
