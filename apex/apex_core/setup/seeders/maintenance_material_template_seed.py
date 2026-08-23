# Copyright (c) 2026, afmcoltd
"""Seed the Maintenance Material catalogue and its default Templates, in that order.

The insert passes ``ignore_permissions`` because a seeder is installer context: it runs from
install and migrate as Administrator, with no session user whose roles could be consulted.

``TEMPLATE_SEEDS`` child rows are REQUIRED Links onto Maintenance Material, so a
template can only be created after every material it names exists — Frappe's
``_validate_links`` walks child rows and rejects the whole document otherwise.
The catalogue has two writers (the module list in
``habitat/doctype/maintenance_material/maintenance_material_catalog.py`` and
``apex_core/setup/data/habitat/maintenance_material.json``, which is the single
source of truth for its 60 records), and the templates reference both. So
``seed_templates`` owns the whole sequence: it runs both material writers first,
which makes the templates independent of where it is called from in the install
order. ``apex_core/setup/test_catalogue_writers.py`` keeps the two writers from
drifting apart, and ``test_material_template_order.py`` keeps this order.
"""
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
    """Run BOTH writers of the Maintenance Material catalogue. Idempotent.

    Both are create-only, so this is safe to call again even though ``seed_all``
    re-applies the JSON later in the same install.
    """
    seed_catalog()
    return seed("habitat", only=["Maintenance Material"])


def seed_templates():
    """Insert default templates if not already present. Idempotent.

    The existence probe is what makes it re-runnable: ``insert`` raises on a name that
    already exists, and this runs on every install AND every migrate.

    ``frappe.db.commit`` (frappe/database/database.py:1173) is called because this runs
    from an install or migrate step: the one thing an uncommitted seed cannot do is
    survive a LATER step failing, and a half-seeded catalog leaves the operator with
    a screen of empty pickers and no error to search for.
    """
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
        doc.insert(ignore_permissions=True)
    frappe.db.commit()
