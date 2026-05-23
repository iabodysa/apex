"""Employee dashboard link data for Apex Habitat.

Called via override_doctype_dashboards in hooks.py to surface housing,
custody, and task records on the ERPNext Employee form dashboard.
"""

from __future__ import annotations


def get_data() -> dict:
    return {
        "fieldname": "employee",
        "non_standard_fieldnames": {},
        "transactions": [
            {
                "label": "Accommodation",
                "items": ["Accommodation Assignment", "Accommodation Checkout"],
            },
            {
                "label": "Custody",
                "items": ["Custody Issue", "Custody Return", "Custody Damage Assessment"],
            },
            {
                "label": "Tasks & Inspection",
                "items": ["Scheduled Task Instance", "Maintenance Inspection Report"],
            },
        ],
    }
