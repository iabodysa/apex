from frappe import _


def get_data():
    return {
        "fieldname": "site",
        "non_standard_fieldnames": {
            "Accommodation Resident Request": "accommodation_site",
            "Accommodation QR Location": "accommodation_site",
        },
        "transactions": [
            {"label": _("Spatial"), "items": ["Accommodation Building"]},
            {"label": _("Residents & Access"), "items": [
                "Accommodation Resident Request", "Accommodation QR Location"]},
        ],
    }
