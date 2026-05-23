from frappe import _

def get_data():
    return {
        "fieldname": "bed",
        "transactions": [
            {
                "label": _("Occupancy & Operations"),
                "items": ["Accommodation Assignment", "Room Bed Transfer"]
            },
            {
                "label": _("Maintenance"),
                "items": ["Maintenance Request", "Maintenance Work Order"]
            }
        ]
    }
