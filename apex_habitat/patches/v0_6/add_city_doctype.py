"""Seed Habitat City with the main Saudi Arabian cities."""

import frappe


SAUDI_CITIES = [
    "Riyadh",
    "Jeddah",
    "Mecca",
    "Medina",
    "Dammam",
    "Khobar",
    "Dhahran",
    "Jubail",
    "Yanbu",
    "Tabuk",
    "Abha",
    "Taif",
    "Buraidah",
    "Hail",
    "Najran",
    "Jizan",
    "Arar",
    "Sakakah",
]


def execute():
    if not frappe.db.exists("DocType", "Habitat City"):
        return

    for city in SAUDI_CITIES:
        if frappe.db.exists("Habitat City", city):
            continue
        doc = frappe.get_doc({
            "doctype": "Habitat City",
            "city_name": city,
            "country": "Saudi Arabia",
        })
        doc.insert(ignore_permissions=True)

    frappe.db.commit()
