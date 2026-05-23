"""Seed default Maintenance Material Templates on fresh install."""
import frappe

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
]


def seed_templates():
    """Insert default templates if not already present. Idempotent."""
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
