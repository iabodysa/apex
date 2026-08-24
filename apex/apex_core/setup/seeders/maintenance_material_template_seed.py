# Copyright (c) 2026, afmcoltd
import frappe

from apex.apex_core.setup.seed import seed
from apex.habitat.doctype.maintenance_material.maintenance_material_catalog import (
    seed_catalog,
)

TEMPLATE_SEEDS = [
    {
        "template_name": "Electrical - Basic",
        "issue_type": "Electrical",
        "items": [
            {"material": "LED Bulbs", "quantity": 4},
            {"material": "Light Switches", "quantity": 2},
            {"material": "Electrical Sockets", "quantity": 2},
            {"material": "Electrical Wires and Cables", "quantity": 5},
            {"material": "Circuit Breakers", "quantity": 1},
        ],
    },
    {
        "template_name": "Air Conditioning - Service",
        "issue_type": "Air Conditioning",
        "items": [
            {"material": "Air Filters", "quantity": 2},
            {"material": "Refrigerant Gas", "quantity": 1},
            {"material": "Capacitor", "quantity": 1},
        ],
    },
    {
        "template_name": "Plumbing - Basic",
        "issue_type": "Plumbing",
        "items": [
            {"material": "Fittings", "quantity": 5},
            {"material": "PVC Sewage Pipes", "quantity": 2},
            {"material": "Pipe Glue", "quantity": 1},
        ],
    },
    {
        "template_name": "Sanitary - Fixture Replacement",
        "issue_type": "Plumbing",
        "items": [
            {"material": "Basin Mixer", "quantity": 1},
            {"material": "Floor Drains", "quantity": 1},
            {"material": "Fittings", "quantity": 3},
        ],
    },
    {
        "template_name": "Fire Safety - Basic",
        "issue_type": "Fire Safety",
        "items": [
            {"material": "Fire Extinguisher", "quantity": 2},
            {"material": "Smoke Detector", "quantity": 2},
            {"material": "Emergency Exit Light", "quantity": 1},
        ],
    },
    {
        "template_name": "Furniture - Room Set",
        "issue_type": "Furniture",
        "items": [
            {"material": "Bed Frame", "quantity": 1},
            {"material": "Mattress", "quantity": 1},
            {"material": "Wardrobe", "quantity": 1},
            {"material": "Chair", "quantity": 1},
        ],
    },
    {
        "template_name": "Pest Control - Basic",
        "issue_type": "Pest Control",
        "items": [
            {"material": "Insecticide Spray", "quantity": 2},
            {"material": "Rodent Trap", "quantity": 3},
            {"material": "Cockroach Gel Bait", "quantity": 2},
        ],
    },
    {
        "template_name": "Structural - Basic Repair",
        "issue_type": "Structural",
        "items": [
            {"material": "Cement Bag", "quantity": 2},
            {"material": "Wall Paint", "quantity": 1},
            {"material": "Gypsum Board", "quantity": 2},
        ],
    },
]


def seed_materials():
    seed_catalog()
    return seed("habitat", only=["Maintenance Material"])


def seed_templates():
    seed_materials()
    for tpl in TEMPLATE_SEEDS:
        if frappe.db.exists("Maintenance Material Template", tpl["template_name"]):
            continue
        doc = frappe.get_doc({
            "doctype": "Maintenance Material Template",
            "template_name": tpl["template_name"],
            "issue_type": tpl["issue_type"],
            "is_active": 1,
            "items": [
                {
                    "material": item["material"],
                    "quantity": item["quantity"],
                }
                for item in tpl["items"]
            ],
        })
        doc.insert()
    frappe.db.commit()
