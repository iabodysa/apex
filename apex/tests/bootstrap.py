# Copyright (c) 2026, afmcoltd

import frappe
from frappe.utils import now_datetime


def before_tests():
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
