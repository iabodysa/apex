# Copyright (c) 2026, afmcoltd

__version__ = "2.10.0"


def check_app_permission() -> bool:
    import frappe
    from frappe.utils.user import is_website_user

    if frappe.session.user == "Administrator":
        return True

    return not is_website_user()
