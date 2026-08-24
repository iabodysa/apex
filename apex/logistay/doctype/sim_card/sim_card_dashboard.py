# Copyright (c) 2026, afmcoltd

from frappe import _


def get_data():
    return {
        "fieldname": "sim_card",
        "transactions": [
            {"label": _("Custody"), "items": ["SIM Custody Assignment"]},
        ],
    }
