# Copyright (c) 2026, AFMCO and contributors
"""Form "Connections" for Telecom Contract: the SIM Cards it governs."""

from frappe import _


def get_data():
    return {
        "fieldname": "telecom_contract",
        "transactions": [
            {"label": _("SIMs"), "items": ["SIM Card"]},
        ],
    }
