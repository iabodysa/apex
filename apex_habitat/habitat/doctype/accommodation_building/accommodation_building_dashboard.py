from frappe import _


def get_data():
    return {
        "fieldname": "building",
        "transactions": [
            {"label": _("Space Management"), "items": ["Accommodation Room", "Accommodation Bed"]},
            {"label": _("Occupancy & Residents"), "items": [
                "Accommodation Assignment", "Accommodation Resident Request",
                "Idle Resident Report", "Accommodation Occupancy Snapshot"]},
            {"label": _("Operations & Maintenance"), "items": [
                "Maintenance Request", "Maintenance Work Order", "Maintenance Inspection Report",
                "Cleaning Log", "Subcontractor Service Order"]},
            {"label": _("Safety & Compliance"), "items": [
                "Building License", "Safety Inspection Report", "Safety Task Execution"]},
            {"label": _("Assets & Custody"), "items": [
                "Facility Asset", "Facility Asset Custody Assignment",
                "Custody Issue", "Custody Return", "Custody Damage Assessment"]},
            {"label": _("Costs & Utilities"), "items": [
                "Accommodation Lease", "Utility Account", "Utility Bill Entry"]},
            {"label": _("Scheduling & Access"), "items": [
                "Scheduled Task Template", "Scheduled Task Instance", "Accommodation QR Location"]},
        ],
    }
