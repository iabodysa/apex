# Copyright (c) 2026, afmcoltd

from frappe import _


def get_data():
    return {
        "fieldname": "telecom_contract",
        "transactions": [
            {"label": _("SIMs"), "items": ["SIM Card"]},
        ],
    }
