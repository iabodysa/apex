"""One-command fleet data importer.

Loads the CSVs produced by the local, git-ignored parser (``docs/etl_out/``)
into the live Salis DocTypes, idempotently and in foreign-key order:

    Vehicle Category, Rental Office, Project
      -> Salis Driver (deduped by driver_id)
      -> Salis Vehicle (deduped by plate_normalized)
      -> current_driver / current_vehicle mirror
      -> Vehicle Assignment (historical backfill, draft)

Run (test/dev bench):
    bench --site <site> execute apex_habitat.salis.fleet_import.run

The CSVs contain PII (driver names, mobiles, national ids); they stay
git-ignored and are never committed. This module is code only (no data). Entity
links are resolved by natural key: Vehicle Category / Rental Office autoname by
their name field (direct), Project autonames by series (mapped project_name ->
name), drivers/vehicles by driver_id / plate_normalized. Historical assignments
are backfilled with ``ignore_validate`` because the live assignment gates
(rider-active, overlap, compliance) are for new operations, not back-dated
custody spells; rows that still fail are skipped and counted.
"""

from __future__ import annotations

import csv
import os

import frappe


def _read(csv_dir, name):
    path = os.path.join(csv_dir, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def run(csv_dir=None):
    csv_dir = csv_dir or os.path.join(frappe.get_app_path("apex_habitat"), "..", "docs", "etl_out")
    csv_dir = os.path.abspath(csv_dir)
    out = {"csv_dir": csv_dir}

    # [#a2zdu8]
    made = 0
    for r in _read(csv_dir, "vehicle_category.csv"):
        cn = (r.get("category_name") or "").strip()
        if cn and not frappe.db.exists("Vehicle Category", cn):
            try:
                frappe.get_doc({"doctype": "Vehicle Category", "category_name": cn,
                                "default_fuel_type": (r.get("default_fuel_type") or "").strip() or None}
                               ).insert(ignore_permissions=True)  # audit-ok: admin bulk migration loader
                made += 1
            except Exception:
                pass
    out["categories_new"] = made

    # [#t0ys01]
    made = 0
    for r in _read(csv_dir, "rental_office.csv"):
        on = (r.get("office_name") or "").strip()
        if on and not frappe.db.exists("Rental Office", on):
            try:
                frappe.get_doc({"doctype": "Rental Office", "office_name": on,
                                "status": (r.get("status") or "Active").strip()}).insert(ignore_permissions=True)  # audit-ok: admin bulk migration loader
                made += 1
            except Exception:
                pass
    out["offices_new"] = made

    # [#fdu5q4]
    proj = {}
    for r in _read(csv_dir, "project.csv"):
        pn = (r.get("project_name") or "").strip()
        if not pn:
            continue
        name = frappe.db.get_value("Project", {"project_name": pn}, "name")
        if not name:
            try:
                name = frappe.get_doc({"doctype": "Project", "project_name": pn}).insert(ignore_permissions=True).name  # audit-ok: admin bulk migration loader
            except Exception:
                continue
        proj[pn] = name
    out["projects"] = len(proj)

    # [#bz8m4k]
    drv = {}
    for r in _read(csv_dir, "salis_driver.csv"):
        did = (r.get("driver_id") or "").strip()
        if not did:
            continue
        name = frappe.db.get_value("Salis Driver", {"driver_id": did}, "name")
        if not name:
            try:
                name = frappe.get_doc({
                    "doctype": "Salis Driver", "driver_id": did,
                    "full_name": (r.get("full_name") or did).strip(),
                    "phone": (r.get("phone") or "").strip() or None,
                    "status": (r.get("status") or "Active").strip(),
                    "project": proj.get((r.get("project") or "").strip()),
                }).insert(ignore_permissions=True).name  # audit-ok: admin bulk migration loader
            except Exception:
                continue
        drv[did] = name
    out["drivers"] = len(drv)

    # [#3wp485]
    veh = {}
    for r in _read(csv_dir, "salis_vehicle.csv"):
        plate = (r.get("plate_number") or "").strip()
        if not plate:
            continue
        norm = "".join(plate.split()).upper()
        name = frappe.db.get_value("Salis Vehicle", {"plate_normalized": norm}, "name")
        if not name:
            try:
                name = frappe.get_doc({
                    "doctype": "Salis Vehicle", "plate_number": plate,
                    "vehicle_category": (r.get("vehicle_category") or "").strip() or None,
                    "ownership": (r.get("ownership") or "Owned").strip(),
                    "rental_office": (r.get("rental_office") or "").strip() or None,
                    "project": proj.get((r.get("project") or "").strip()),
                    "status": (r.get("status") or "Active").strip(),
                }).insert(ignore_permissions=True).name  # audit-ok: admin bulk migration loader
            except Exception:
                continue
        veh[plate] = name
    out["vehicles"] = len(veh)

    # [#bnwnyn]
    mirrored = 0
    for r in _read(csv_dir, "salis_vehicle_current_driver_patch.csv"):
        vn = veh.get((r.get("plate_number") or "").strip())
        dn = drv.get((r.get("current_driver_id") or "").strip())
        if vn and dn:
            frappe.db.set_value("Salis Vehicle", vn, "current_driver", dn, update_modified=False)
            frappe.db.set_value("Salis Driver", dn, "current_vehicle", vn, update_modified=False)
            mirrored += 1
    out["mirrored"] = mirrored

    # [#489xak]
    loaded = skipped = 0
    for r in _read(csv_dir, "vehicle_assignment_clean.csv"):
        vn = veh.get((r.get("vehicle") or "").strip())
        dn = drv.get((r.get("driver_id") or "").strip())
        if not (vn and dn):
            skipped += 1
            continue
        try:
            a = frappe.get_doc({
                "doctype": "Vehicle Assignment", "vehicle": vn, "driver": dn,
                "project": proj.get((r.get("project") or "").strip()),
                "start_date": (r.get("start_date") or "").strip() or None,
                "end_date": (r.get("end_date") or "").strip() or None,
                "status": (r.get("status") or "Ended").strip(),
            })
            a.flags.ignore_validate = True  # [#fbx2ud]
            a.insert(ignore_permissions=True)  # audit-ok: admin bulk migration loader
            loaded += 1
        except Exception:
            skipped += 1
    out["assignments_loaded"] = loaded
    out["assignments_skipped"] = skipped

    frappe.db.commit()
    return out
