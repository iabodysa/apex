# Copyright (c) 2026, afmcoltd
"""
Apex

Frappe Framework v15 application providing the Habitat, Salis, Logistay and
Apex Core modules.
"""

__version__ = "2.7.0"


def check_app_permission() -> bool:
    """Gate for the Apex desk tile on /apps.

    Mirrors ``erpnext.check_app_permission`` (erpnext/__init__.py:155): the tile leads
    to ``/app``, which a Website User cannot open at all, so the only thing worth
    asking is whether this account reaches the desk. Which WORKSPACE it lands on is
    not decided here — ``frappe.apps.get_route`` (frappe/apps.py:53) already falls back
    to the first workspace the user is allowed, so a narrower check here would hide the
    desk from someone who has one.
    """
    import frappe
    from frappe.utils.user import is_website_user

    if frappe.session.user == "Administrator":
        return True

    return not is_website_user()
