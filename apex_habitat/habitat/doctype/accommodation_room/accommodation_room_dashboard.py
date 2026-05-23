from frappe import _

def get_data():
    return {
        "fieldname": "room",
        "transactions": [
            {
                "label": _("Space Management"),
                "items": ["Accommodation Bed"]
            },
            {
                "label": _("Occupancy & Operations"),
                "items": ["Accommodation Assignment", "Room Bed Transfer", "Cleaning Log"]
            },
            {
                "label": _("Maintenance"),
                "items": ["Maintenance Request", "Maintenance Work Order"]
            }
        ]
    }
