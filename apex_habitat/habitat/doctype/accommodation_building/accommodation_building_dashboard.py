from frappe import _

def get_data():
    return {
        "fieldname": "building",
        "transactions": [
            {
                "label": _("Space Management"),
                "items": ["Accommodation Room", "Accommodation Bed"]
            },
            {
                "label": _("Occupancy & Residents"),
                "items": ["Accommodation Assignment", "Accommodation Resident Request",
                          "Accommodation Occupancy Snapshot"]
            },
            {
                "label": _("Operations & Maintenance"),
                "items": ["Maintenance Request", "Maintenance Work Order", "Cleaning Log"]
            },
            {
                "label": _("Assets & Custody"),
                "items": ["Facility Asset", "Custody Issue", "Custody Return"]
            },
            {
                "label": _("Financials & Compliance"),
                "items": ["Building License", "Accommodation Lease", "Utility Account", "Utility Bill Entry"]
            }
        ]
    }
