# Copyright (c) 2026, AFMCO and contributors
"""Form "Connections" for SIM Card: its custody history."""

from frappe import _


def get_data():
    return {
        "fieldname": "sim_card",
        "transactions": [
            {"label": _("Custody"), "items": ["SIM Custody Assignment"]},
        ],
    }
