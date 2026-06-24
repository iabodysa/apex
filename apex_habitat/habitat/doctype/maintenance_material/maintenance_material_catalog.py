"""Seed the Maintenance Material catalog on fresh install."""
import frappe


MAINTENANCE_MATERIAL_CATALOG = [
    # [#1b5mxp]
    {"material_name": "Electrical Wires and Cables", "material_category": "Electrical", "default_uom": "Meter"},
    {"material_name": "Distribution Board", "material_category": "Electrical", "default_uom": "Piece"},
    {"material_name": "Electrical Junction Boxes", "material_category": "Electrical", "default_uom": "Piece"},
    {"material_name": "Cable Conduits", "material_category": "Electrical", "default_uom": "Meter"},
    {"material_name": "Circuit Breakers", "material_category": "Electrical", "default_uom": "Piece"},
    {"material_name": "Earth Leakage Breaker", "material_category": "Electrical", "default_uom": "Piece"},
    {"material_name": "Light Switches", "material_category": "Electrical", "default_uom": "Piece"},
    {"material_name": "Electrical Sockets", "material_category": "Electrical", "default_uom": "Piece"},
    {"material_name": "Power Sockets", "material_category": "Electrical", "default_uom": "Piece"},
    {"material_name": "Spotlights", "material_category": "Electrical", "default_uom": "Piece"},
    {"material_name": "LED Bulbs", "material_category": "Electrical", "default_uom": "Piece"},
    {"material_name": "LED Strip Lights", "material_category": "Electrical", "default_uom": "Meter"},
    {"material_name": "Wall/Ceiling Lights", "material_category": "Electrical", "default_uom": "Piece"},
    # [#kjglku]
    {"material_name": "Compressor", "material_category": "Air Conditioning", "default_uom": "Piece"},
    {"material_name": "Capacitor", "material_category": "Air Conditioning", "default_uom": "Piece"},
    {"material_name": "Contactor", "material_category": "Air Conditioning", "default_uom": "Piece"},
    {"material_name": "Electronic Board", "material_category": "Air Conditioning", "default_uom": "Piece"},
    {"material_name": "Refrigerant Gas", "material_category": "Air Conditioning", "default_uom": "Kg"},
    {"material_name": "Expansion Valve", "material_category": "Air Conditioning", "default_uom": "Piece"},
    {"material_name": "Heat Exchanger", "material_category": "Air Conditioning", "default_uom": "Piece"},
    {"material_name": "Fan Motor", "material_category": "Air Conditioning", "default_uom": "Piece"},
    {"material_name": "Louvers", "material_category": "Air Conditioning", "default_uom": "Piece"},
    {"material_name": "Air Filters", "material_category": "Air Conditioning", "default_uom": "Piece"},
    # [#bjimb8]
    {"material_name": "Thermal Pipes", "material_category": "Plumbing", "default_uom": "Meter"},
    {"material_name": "PVC Sewage Pipes", "material_category": "Plumbing", "default_uom": "Meter"},
    {"material_name": "Fittings", "material_category": "Plumbing", "default_uom": "Piece"},
    {"material_name": "Burial Valves", "material_category": "Plumbing", "default_uom": "Piece"},
    {"material_name": "Pipe Glue", "material_category": "Plumbing", "default_uom": "Can"},
    # [#670f60]
    {"material_name": "Sink Basins", "material_category": "Sanitary Fixtures", "default_uom": "Piece"},
    {"material_name": "Toilets", "material_category": "Sanitary Fixtures", "default_uom": "Piece"},
    {"material_name": "Bathtub or Shower Box", "material_category": "Sanitary Fixtures", "default_uom": "Piece"},
    {"material_name": "Basin Mixer", "material_category": "Sanitary Fixtures", "default_uom": "Piece"},
    {"material_name": "Bidet Mixer", "material_category": "Sanitary Fixtures", "default_uom": "Piece"},
    {"material_name": "Shower Mixer", "material_category": "Sanitary Fixtures", "default_uom": "Piece"},
    {"material_name": "Hand Shower", "material_category": "Sanitary Fixtures", "default_uom": "Piece"},
    {"material_name": "Floor Drains", "material_category": "Sanitary Fixtures", "default_uom": "Piece"},
    {"material_name": "Soap Dispenser", "material_category": "Sanitary Fixtures", "default_uom": "Piece"},
    {"material_name": "Towel Holders", "material_category": "Sanitary Fixtures", "default_uom": "Piece"},
]


def seed_catalog():
    """Insert catalog items if not already present. Idempotent."""
    for item in MAINTENANCE_MATERIAL_CATALOG:
        if frappe.db.exists("Maintenance Material", item["material_name"]):
            continue
        doc = frappe.get_doc({
            "doctype": "Maintenance Material",
            "material_name": item["material_name"],
            "material_category": item["material_category"],
            "default_uom": item.get("default_uom", "Piece"),
            "is_active": 1,
        })
        doc.insert(ignore_permissions=True)
    frappe.db.commit()


# Single tree root; each category Select option becomes a group node beneath it.
MATERIAL_ROOT = "All Maintenance Materials"
MATERIAL_CATEGORIES = [
    "Electrical", "Air Conditioning", "Plumbing",
    "Sanitary Fixtures", "Furniture", "General",
]


def _ensure_group(name, category, parent):
    if not frappe.db.exists("Maintenance Material", name):
        frappe.get_doc({
            "doctype": "Maintenance Material",
            "material_name": name,
            "material_category": category,
            "is_group": 1,
            "is_active": 1,
            "parent_maintenance_material": parent,
        }).insert(ignore_permissions=True)


def seed_tree_groups():
    """Build a single-root group hierarchy and nest leaf materials by category. Idempotent.

    Re-parent existing flat leaves BEFORE inserting the root so validate_one_root
    sees a single root (db.set_value bypasses the controller and link check).
    """
    from frappe.utils.nestedset import rebuild_tree

    group_of = {c: f"{c} Materials" for c in MATERIAL_CATEGORIES}
    leaves = frappe.get_all(
        "Maintenance Material",
        filters={"is_group": 0, "parent_maintenance_material": ["in", ["", None]]},
        fields=["name", "material_category"],
    )
    for leaf in leaves:
        frappe.db.set_value("Maintenance Material", leaf.name,
                            "parent_maintenance_material",
                            group_of.get(leaf.material_category, group_of["General"]),
                            update_modified=False)

    _ensure_group(MATERIAL_ROOT, "General", "")
    for category in MATERIAL_CATEGORIES:
        _ensure_group(group_of[category], category, MATERIAL_ROOT)

    rebuild_tree("Maintenance Material")
    frappe.db.commit()
