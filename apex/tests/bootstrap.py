# Copyright (c) 2026, afmcoltd
"""What a fresh site needs before any apex test can run.

``frappe.test_runner`` asks for the hook of the app UNDER TEST only —
``frappe.get_hooks("before_tests", app_name=app)`` at frappe/test_runner.py:86 — so
running ``--app apex`` never fires the hooks erpnext and hrms declare for themselves.
Without one of them, nothing has run the setup wizard, and the records it seeds are
absent: the first test to insert a Company reaches
``erpnext.setup.doctype.company.company.create_default_warehouses``, which builds a
"Goods In Transit" warehouse and fails on a missing ``Warehouse Type: Transit``
(install_fixtures.py:289 is the only place that record is created).

A developer bench never shows this, because its setup wizard was completed by hand long
ago and the records have been there ever since. It appears the first time the suite runs
somewhere clean.

The values are apex's own rather than erpnext's: its fixture company is USD and United
States, and this app's tests read money in the site currency.
"""

import frappe
from frappe.utils import now_datetime


def before_tests():
    """Complete the setup wizard once, so the records erpnext's own controllers need exist."""
    frappe.clear_cache()

    if not frappe.db.a_row_exists("Company"):
        from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

        year = now_datetime().year
        setup_complete(
            {
                "currency": "SAR",
                "full_name": "Test User",
                "company_name": "_Test Company",
                "company_abbr": "_TC",
                "timezone": "Asia/Riyadh",
                "industry": "Services",
                "country": "Saudi Arabia",
                "fy_start_date": f"{year}-01-01",
                "fy_end_date": f"{year}-12-31",
                "language": "english",
                "company_tagline": "Testing",
                "email": "test@example.com",
                "password": "test",
                "chart_of_accounts": "Standard",
            }
        )

    frappe.db.commit()
