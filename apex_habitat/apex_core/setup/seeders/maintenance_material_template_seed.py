"""Seed default Maintenance Material Templates on fresh install."""
import frappe

# Catalog materials needed by the templates below that are not part of the
# original Electrical/AC/Plumbing/Sanitary seed. Categories are limited to the
# Maintenance Material select options (Furniture and General are the available
# buckets for these issue types).
MATERIAL_SEEDS = [
    # Fire Safety
    {"material_name": "Fire Extinguisher", "material_category": "General"},
    {"material_name": "Smoke Detector", "material_category": "General"},
    {"material_name": "Fire Alarm Panel", "material_category": "General"},
    {"material_name": "Fire Hose Reel", "material_category": "General"},
    {"material_name": "Emergency Exit Light", "material_category": "General"},
    # Furniture
    {"material_name": "Bed Frame", "material_category": "Furniture"},
    {"material_name": "Mattress", "material_category": "Furniture"},
    {"material_name": "Wardrobe", "material_category": "Furniture"},
    {"material_name": "Study Desk", "material_category": "Furniture"},
    {"material_name": "Chair", "material_category": "Furniture"},
    # Pest Control
    {"material_name": "Insecticide Spray", "material_category": "General"},
    {"material_name": "Rodent Trap", "material_category": "General"},
    {"material_name": "Cockroach Gel Bait", "material_category": "General"},
    # Structural
    {"material_name": "Cement Bag", "material_category": "General"},
    {"material_name": "Wall Paint", "material_category": "General"},
    {"material_name": "Gypsum Board", "material_category": "General"},
    {"material_name": "Door Lock", "material_category": "General"},
]

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
    """Insert catalog materials required by the templates. Idempotent."""
    for mat in MATERIAL_SEEDS:
        if frappe.db.exists("Maintenance Material", mat["material_name"]):
            continue
        frappe.get_doc({
            "doctype": "Maintenance Material",
            "material_name": mat["material_name"],
            "material_category": mat["material_category"],
            "is_active": 1,
        }).insert(ignore_permissions=True)


def seed_templates():
    """Insert default templates if not already present. Idempotent."""
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
