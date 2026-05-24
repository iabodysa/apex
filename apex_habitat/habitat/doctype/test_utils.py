"""Shared test fixture helpers for Habitat doctypes.

Usage:
    from apex_habitat.habitat.doctype.test_utils import make_building, make_room, make_bed, make_assignment
"""

from __future__ import annotations
import frappe


def make_company(name="Test AFMCO", **kwargs):
    if frappe.db.exists("Company", name):
        return frappe.get_doc("Company", name)
    doc = frappe.get_doc({
        "doctype": "Company",
        "company_name": name,
        "abbr": "TAFM",
        "default_currency": "SAR",
        **kwargs,
    })
    doc.insert(ignore_permissions=True)
    return doc


def make_building(name=None, company=None, **kwargs):
    name = name or "Test Building"
    if frappe.db.exists("Accommodation Building", name):
        return frappe.get_doc("Accommodation Building", name)
    doc = frappe.get_doc({
        "doctype": "Accommodation Building",
        "building_name": name,
        "status": "Active",
        "total_capacity": kwargs.pop("total_capacity", 10),
        "company": company or "Test AFMCO",
        **kwargs,
    })
    doc.insert(ignore_permissions=True)
    return doc


def make_room(building, room_number=None, **kwargs):
    room_number = room_number or f"{building}-R01"
    if frappe.db.exists("Accommodation Room", room_number):
        return frappe.get_doc("Accommodation Room", room_number)
    doc = frappe.get_doc({
        "doctype": "Accommodation Room",
        "room_number": room_number,
        "building": building,
        "bed_capacity": kwargs.pop("bed_capacity", 2),
        "status": "Available",
        **kwargs,
    })
    doc.insert(ignore_permissions=True)
    return doc


def make_bed(room, bed_code=None, **kwargs):
    bed_code = bed_code or f"{room}-B01"
    if frappe.db.exists("Accommodation Bed", bed_code):
        return frappe.get_doc("Accommodation Bed", bed_code)
    doc = frappe.get_doc({
        "doctype": "Accommodation Bed",
        "bed_code": bed_code,
        "room": room,
        "status": "Available",
        **kwargs,
    })
    doc.insert(ignore_permissions=True)
    return doc


def make_employee(name=None, company=None, **kwargs):
    name = name or "Test Employee"
    if frappe.db.exists("Employee", {"employee_name": name}):
        return frappe.get_all("Employee", filters={"employee_name": name}, limit=1)[0]
    doc = frappe.get_doc({
        "doctype": "Employee",
        "employee_name": name,
        "company": company or "Test AFMCO",
        "status": "Active",
        "gender": "Male",
        "date_of_birth": "1990-01-01",
        "date_of_joining": "2020-01-01",
        **kwargs,
    })
    doc.insert(ignore_permissions=True)
    return doc
