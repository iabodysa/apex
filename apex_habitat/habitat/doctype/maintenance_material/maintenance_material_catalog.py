"""Seed the Maintenance Material catalog on fresh install."""
import frappe


MAINTENANCE_MATERIAL_CATALOG = [
    # Electrical (13)
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
    # Air Conditioning (10)
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
    # Plumbing (5)
    {"material_name": "Thermal Pipes", "material_category": "Plumbing", "default_uom": "Meter"},
    {"material_name": "PVC Sewage Pipes", "material_category": "Plumbing", "default_uom": "Meter"},
    {"material_name": "Fittings", "material_category": "Plumbing", "default_uom": "Piece"},
    {"material_name": "Burial Valves", "material_category": "Plumbing", "default_uom": "Piece"},
    {"material_name": "Pipe Glue", "material_category": "Plumbing", "default_uom": "Can"},
    # Sanitary Fixtures (10)
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
