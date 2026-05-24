# Copyright (c) 2026, AFMCO and contributors
# QA PROBE — temporary module. Probes maintenance/safety logic, reports,
# scheduled jobs, and onboarding permissions.

import frappe
from apex_habitat.tests.test_utils import ApexHabitatTestCase


def _hash(n=4):
    return frappe.generate_hash(length=n).upper()


class QASysBase(ApexHabitatTestCase):
    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Company",
            "default_currency": "SAR", "country": "Saudi Arabia",
        }).insert(ignore_permissions=True).name
        self.cost_center = (
            frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company})
            or frappe.db.get_value("Cost Center", {"is_group": 0})
        )
        self.site = frappe.get_doc({
            "doctype": "Accommodation Site", "site_name": _hash(6),
        }).insert(ignore_permissions=True)

    def _make_building(self):
        abbr = "S" + _hash(3)
        b = frappe.get_doc({
            "doctype": "Accommodation Building",
            "building_name": f"Bldg {abbr}", "abbreviation": abbr,
            "site": self.site.name, "total_capacity": 50,
            "default_cost_center": self.cost_center,
        })
        b.insert(ignore_permissions=True)
        return b

    def _room(self, building):
        return frappe.get_doc({
            "doctype": "Accommodation Room", "naming_series": "ROOM-.####",
            "building": building, "room_number": "R" + _hash(), "bed_capacity": 2,
        }).insert(ignore_permissions=True).name


class TestMaintenanceSafety(QASysBase):
    # Scenario 6a: Maintenance Request with issue_type Fire Safety + load_template_into_doc loads rows
    def test_6a_load_template_fire_safety(self):
        from apex_habitat.habitat.doctype.maintenance_material_template.maintenance_material_template import (
            load_template_into_doc,
        )
        # Build a Fire Safety material template with one material
        mat = frappe.get_doc({
            "doctype": "Maintenance Material", "material_name": "Extinguisher " + _hash(),
            "material_category": "General",
        }).insert(ignore_permissions=True)
        tpl = frappe.get_doc({
            "doctype": "Maintenance Material Template",
            "template_name": "Fire Safety Kit " + _hash(),
            "issue_type": "Fire Safety", "is_active": 1,
        })
        tpl.append("items", {"material": mat.name, "quantity": 2, "unit": "Piece"})
        tpl.insert(ignore_permissions=True)

        b = self._make_building()
        room = self._room(b.name)
        mr = frappe.get_doc({
            "doctype": "Maintenance Request", "naming_series": "MAINT-.YYYY.-.#####",
            "building": b.name, "room": room, "reported_by": "Administrator",
            "issue_type": "Fire Safety", "issue_description": "fire check", "status": "Open",
        })
        mr.insert(ignore_permissions=True)

        res = load_template_into_doc("Maintenance Request", mr.name, "Fire Safety")
        mr.reload()
        print(f"\n[6a] load_template result={res}, procurement_items rows={len(mr.procurement_items)}")
        self.assertGreaterEqual(res.get("rows_added", 0), 1, "BUG: Fire Safety template loaded 0 rows")
        self.assertGreaterEqual(len(mr.procurement_items), 1)

    # Scenario 6b (FIXED): submit keeps Open; start_task -> In Progress; mark_completed -> Completed.
    def test_6b_task_lifecycle_open_inprogress_completed(self):
        from apex_habitat.habitat.doctype.scheduled_task_instance.scheduled_task_instance import (
            start_task, mark_completed,
        )
        b = self._make_building()
        tmpl = frappe.get_doc({
            "doctype": "Scheduled Task Template", "template_name": "T " + _hash(),
            "task_type": "Safety", "building": b.name, "frequency": "Monthly", "is_active": 1,
        }).insert(ignore_permissions=True)
        sti = frappe.get_doc({
            "doctype": "Scheduled Task Instance", "template": tmpl.name,
            "due_date": "2026-05-31", "status": "Open",
        })
        sti.insert(ignore_permissions=True)
        sti.submit()
        sti.reload()
        print(f"\n[6b] status after submit={sti.status}")
        self.assertEqual(sti.status, "Open", "submit must NOT auto-complete the task")

        start_task(sti.name)
        sti.reload()
        self.assertEqual(sti.status, "In Progress", "start_task must move Open -> In Progress")

        mark_completed(sti.name)
        sti.reload()
        self.assertEqual(sti.status, "Completed", "mark_completed must move In Progress -> Completed")


class TestReports(QASysBase):
    REPORTS = [
        "accommodation_ledger_summary",
        "accommodation_occupancy_summary",
        "checkout_pending_clearance",
        "utility_variance_report",
        "operational_depreciation_aging",
        "lease_expiry_watchlist",
        "daily_cleaning_compliance",
    ]

    def _execute(self, report_module, filters):
        mod = frappe.get_module(
            f"apex_habitat.habitat.report.{report_module}.{report_module}"
        )
        return mod.execute(filters)

    def test_7_reports_empty_and_dated(self):
        from frappe.utils import today, add_days
        date_filters = {"from_date": add_days(today(), -30), "to_date": today()}
        failures = []
        for r in self.REPORTS:
            for label, flt in (("empty", {}), ("dated", date_filters)):
                try:
                    result = self._execute(r, flt)
                    columns = result[0] if result else None
                    print(f"\n[7] {r} ({label}): columns={len(columns) if columns else 0}, rows={len(result[1]) if result and len(result) > 1 else 0}")
                    if not columns:
                        failures.append(f"{r}/{label}: no columns returned")
                except Exception as e:
                    failures.append(f"{r}/{label}: {type(e).__name__}: {e}")
                    print(f"\n[7] BUG {r} ({label}) CRASHED: {type(e).__name__}: {e}")
        if failures:
            print("\n[7] REPORT FAILURES:\n  " + "\n  ".join(failures))
        self.assertEqual(failures, [], f"Report failures: {failures}")


class TestSchedulers(QASysBase):
    JOBS = [
        "daily_accommodation_cost_allocation",
        "daily_building_license_expiry_check",
        "open_maintenance_escalation",
        "lease_expiry_watchlist",
        "daily_scheduled_task_instance_generator",
        "weekly_occupancy_sync",
        "weekly_safety_task_compliance_scan",
        "monthly_rent_due_alert",
    ]

    def test_8_all_schedulers_run(self):
        import apex_habitat.habitat.tasks as tasks
        errlog_before = frappe.db.count("Error Log")
        failures = []
        for job in self.JOBS:
            fn = getattr(tasks, job)
            try:
                fn()
                print(f"\n[8] {job}: OK")
            except Exception as e:
                failures.append(f"{job}: {type(e).__name__}: {e}")
                print(f"\n[8] BUG {job} RAISED: {type(e).__name__}: {e}")
        errlog_after = frappe.db.count("Error Log")
        print(f"\n[8] Error Log rows before={errlog_before} after={errlog_after} (delta={errlog_after - errlog_before})")
        self.assertEqual(failures, [], f"Scheduler failures: {failures}")


class TestOnboardingSafetyCatalog(QASysBase):
    # Scenario 9: investigate the "Review the Safety Task Catalog" onboarding step
    def test_9_safety_catalog_permissions_and_route(self):
        meta = frappe.get_meta("Safety Task Catalog")
        roles_with_read = [p.role for p in meta.permissions if p.read]
        print(f"\n[9] Safety Task Catalog roles with read={roles_with_read}")
        print(f"[9] istable={meta.istable} read_only={getattr(meta, 'read_only', None)}")

        # Check the onboarding step config
        if frappe.db.exists("Onboarding Step", "Review the Safety Task Catalog"):
            step = frappe.get_doc("Onboarding Step", "Review the Safety Task Catalog")
            print(f"[9] step action={step.action} reference_document={step.reference_document} is_complete={step.is_complete}")
            ref_exists = frappe.db.exists("DocType", step.reference_document)
            print(f"[9] reference DocType '{step.reference_document}' exists={bool(ref_exists)}")
        else:
            print("[9] Onboarding Step 'Review the Safety Task Catalog' NOT found in DB.")

        # Probe has_permission as each role using a temporary user
        for role in ("Accommodation Manager", "Resident Supervisor"):
            if not frappe.db.exists("Role", role):
                print(f"[9] Role '{role}' does NOT exist in this site. (Likely cause of broken onboarding action if roles never installed.)")
                continue
            email = f"qa_{_hash()}@example.com"
            user = frappe.get_doc({
                "doctype": "User", "email": email, "first_name": "QA",
                "send_welcome_email": 0, "roles": [{"role": role}],
            })
            user.insert(ignore_permissions=True)
            try:
                frappe.set_user(email)
                has_read = frappe.has_permission("Safety Task Catalog", "read")
                # Simulate the list-view permission (what the onboarding "View List" action needs)
                can_get_list = True
                list_err = None
                try:
                    frappe.get_list("Safety Task Catalog", limit=1)
                except Exception as e:
                    can_get_list = False
                    list_err = str(e)
                print(f"[9] role={role} has_permission(read)={has_read} get_list_ok={can_get_list} err={list_err}")
            finally:
                frappe.set_user("Administrator")

        # Is the doctype attached to any workspace / module the roles can see?
        module = frappe.db.get_value("DocType", "Safety Task Catalog", "module")
        print(f"[9] Safety Task Catalog module={module}")
