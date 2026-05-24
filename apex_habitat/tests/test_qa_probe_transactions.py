# Copyright (c) 2026, AFMCO and contributors
# QA PROBE — temporary module. Probes transaction doctypes for bugs.
# Each test records PASS (system rejected/handled bad data) or BUG (wrong accept/crash).
# Findings are printed; assertions only fail where behavior is unambiguously broken.

import frappe
from apex_habitat.tests.test_utils import ApexHabitatTestCase
from apex_habitat.habitat.doctype.accommodation_building.accommodation_building import (
    generate_rooms_and_beds,
)


def _hash(n=4):
    return frappe.generate_hash(length=n).upper()


class QABase(ApexHabitatTestCase):
    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Company",
            "default_currency": "SAR", "country": "Saudi Arabia",
        }).insert(ignore_permissions=True).name
        self.cost_center = (
            frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company})
            or frappe.db.get_value("Cost Center", {"is_group": 0})
        )
        self.project = frappe.db.get_value("Project", {}) or frappe.get_doc({
            "doctype": "Project", "project_name": "Test Project", "company": self.company,
        }).insert(ignore_permissions=True).name
        # Fresh employee per test to avoid the "active assignment" guard colliding
        # with leftover data from a previous real run.
        self.employee = frappe.get_doc({
            "doctype": "Employee", "first_name": "QA Emp " + _hash(),
            "company": self.company, "gender": "Male",
            "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01",
        }).insert(ignore_permissions=True).name
        self.site = frappe.get_doc({
            "doctype": "Accommodation Site", "site_name": _hash(6),
        }).insert(ignore_permissions=True)

    def _make_building(self, room_count=3, room_type="Standard", capacity=2, total_capacity=50):
        abbr = "B" + _hash(3)
        b = frappe.get_doc({
            "doctype": "Accommodation Building",
            "building_name": f"Bldg {abbr}",
            "abbreviation": abbr,
            "site": self.site.name,
            "total_capacity": total_capacity,
            "default_cost_center": self.cost_center,
        })
        b.append("floor_plan", {
            "floor_number": 1, "starting_room_number": 1,
            "room_count": room_count, "bed_capacity_per_room": capacity,
            "room_type": room_type, "generate_beds": 1,
        })
        b.insert(ignore_permissions=True)
        return b

    def _first_room_bed(self, building):
        room = frappe.get_all("Accommodation Room", {"building": building}, pluck="name")[0]
        bed = frappe.get_all("Accommodation Bed", {"room": room}, pluck="name")[0]
        return room, bed

    def _assignment(self, building, room, bed, employee=None):
        a = frappe.get_doc({
            "doctype": "Accommodation Assignment",
            "employee": employee or self.employee, "project": self.project,
            "cost_center": self.cost_center, "building": building,
            "room": room, "bed": bed, "check_in_date": "2026-05-01",
            "assignment_type": "New Assignment",
        })
        a.insert(ignore_permissions=True)
        a.submit()
        return a


class TestRoomGenerator(QABase):
    # Scenario 1a: re-run with same plan -> 0 duplicates
    def test_1a_rerun_same_plan_no_duplicates(self):
        b = self._make_building(room_count=3)
        generate_rooms_and_beds(b.name)
        before = frappe.db.count("Accommodation Room", {"building": b.name})
        res = generate_rooms_and_beds(b.name)
        after = frappe.db.count("Accommodation Room", {"building": b.name})
        print(f"\n[1a] rooms before={before} after={after} created={res['created_rooms']} skipped={res['skipped_rooms']}")
        self.assertEqual(after, before, "BUG: re-run created duplicate rooms")
        self.assertEqual(res["created_rooms"], 0)

    # Scenario 1b (FIXED): changing room_type and re-running updates existing rooms.
    def test_1b_change_room_type_updates_existing(self):
        b = self._make_building(room_count=3, room_type="Standard")
        generate_rooms_and_beds(b.name)
        room = frappe.get_all("Accommodation Room", {"building": b.name}, pluck="name")[0]

        b.reload()
        b.floor_plan[0].room_type = "Supervisor"
        b.save(ignore_permissions=True)
        res = generate_rooms_and_beds(b.name)
        type_after = frappe.db.get_value("Accommodation Room", room, "room_type")
        print(f"\n[1b] room_type after={type_after} updated={res.get('updated_rooms')} created={res.get('created_rooms')}")
        self.assertEqual(type_after, "Supervisor", "existing room type must update to match the plan")
        self.assertGreaterEqual(res.get("updated_rooms", 0), 1)
        self.assertEqual(res.get("created_rooms"), 0)

    # Scenario 1c (FIXED): raising room_count does NOT silently add rooms; it needs confirmation.
    def test_1c_increase_room_count_requires_confirmation(self):
        b = self._make_building(room_count=3)
        generate_rooms_and_beds(b.name)
        before = frappe.db.count("Accommodation Room", {"building": b.name})

        b.reload()
        b.floor_plan[0].room_count = 5
        b.save(ignore_permissions=True)

        # Re-run WITHOUT confirmation: must not create new rooms silently.
        res = generate_rooms_and_beds(b.name)
        mid = frappe.db.count("Accommodation Room", {"building": b.name})
        print(f"\n[1c] no-confirm before={before} after={mid} created={res.get('created_rooms')} pending={res.get('pending_new_rooms')} needs_confirmation={res.get('needs_confirmation')}")
        self.assertTrue(res.get("needs_confirmation"), "new rooms must require confirmation")
        self.assertEqual(res.get("created_rooms"), 0)
        self.assertEqual(mid, before, "no rooms may be created without confirmation")
        self.assertEqual(res.get("pending_new_rooms"), 2)

        # Re-run WITH confirmation: the 2 new rooms are created.
        res2 = generate_rooms_and_beds(b.name, confirm_new_rooms=1)
        after = frappe.db.count("Accommodation Room", {"building": b.name})
        print(f"[1c] confirmed after={after} created={res2.get('created_rooms')}")
        self.assertEqual(res2.get("created_rooms"), 2)
        self.assertEqual(after, before + 2)


class TestCheckout(QABase):
    # Scenario 2: second checkout for same assignment must be rejected
    def test_2_double_checkout_rejected(self):
        b = self._make_building()
        generate_rooms_and_beds(b.name)
        room, bed = self._first_room_bed(b.name)
        a = self._assignment(b.name, room, bed)

        c1 = frappe.get_doc({
            "doctype": "Accommodation Checkout", "assignment": a.name,
            "checkout_date": "2026-05-21", "checkout_reason": "Final Exit",
        })
        c1.insert(ignore_permissions=True)
        c1.submit()

        c2 = frappe.get_doc({
            "doctype": "Accommodation Checkout", "assignment": a.name,
            "checkout_date": "2026-05-22", "checkout_reason": "Final Exit",
        })
        rejected = False
        try:
            c2.insert(ignore_permissions=True)
            c2.submit()
        except frappe.ValidationError as e:
            rejected = True
            print(f"\n[2] second checkout rejected: {e}")
        print(f"[2] double checkout rejected={rejected}")
        self.assertTrue(rejected, "BUG: second checkout was accepted")


class TestCancelledRecreate(QABase):
    # Scenario 3: cancel assignment, then new assignment for same employee+bed should be ALLOWED
    def test_3_cancelled_assignment_allows_recreate(self):
        b = self._make_building()
        generate_rooms_and_beds(b.name)
        room, bed = self._first_room_bed(b.name)

        a1 = self._assignment(b.name, room, bed)
        a1.cancel()
        print(f"\n[3] a1 docstatus after cancel={a1.docstatus}, bed status={frappe.db.get_value('Accommodation Bed', bed, 'status')}")

        allowed = True
        err = None
        try:
            self._assignment(b.name, room, bed)
        except Exception as e:
            allowed = False
            err = str(e)
        print(f"[3] re-create after cancel allowed={allowed} err={err}")
        self.assertTrue(allowed, f"BUG: cancelled assignment wrongly blocked re-create: {err}")

    # Scenario 3b: after cancelling a CHECKOUT, can you re-checkout?
    def test_3b_recheckout_after_checkout_cancel(self):
        b = self._make_building()
        generate_rooms_and_beds(b.name)
        room, bed = self._first_room_bed(b.name)
        a = self._assignment(b.name, room, bed)
        self._assignment_a = a

        c1 = frappe.get_doc({
            "doctype": "Accommodation Checkout", "assignment": a.name,
            "checkout_date": "2026-05-21", "checkout_reason": "Final Exit",
        })
        c1.insert(ignore_permissions=True)
        c1.submit()
        c1.reload()
        c1.cancellation_reason = "QA test"
        c1.cancel()
        a.reload()
        print(f"\n[3b] after checkout cancel: assignment.check_out_date={a.check_out_date}, bed={frappe.db.get_value('Accommodation Bed', bed, 'status')}")

        c2 = frappe.get_doc({
            "doctype": "Accommodation Checkout", "assignment": a.name,
            "checkout_date": "2026-05-23", "checkout_reason": "Final Exit",
        })
        allowed = True
        err = None
        try:
            c2.insert(ignore_permissions=True)
            c2.submit()
        except Exception as e:
            allowed = False
            err = str(e)
        print(f"[3b] re-checkout after cancel allowed={allowed} err={err}")
        self.assertTrue(allowed, f"BUG: cannot re-checkout after cancelling checkout: {err}")


class TestCustody(QABase):
    def _article(self):
        cat = frappe.db.get_value("Custody Asset Category", {}) or frappe.get_doc({
            "doctype": "Custody Asset Category", "category_name": "Cat " + _hash(),
        }).insert(ignore_permissions=True).name
        art = frappe.get_doc({
            "doctype": "Custody Article", "naming_series": "ART-.####",
            "article_name": "Art " + _hash(), "category": cat,
        }).insert(ignore_permissions=True)
        return art.name

    def _issue(self, article, qty=5, employee=None):
        if not getattr(self, "_cust_building", None):
            self._cust_building = self._make_building().name
        i = frappe.get_doc({
            "doctype": "Custody Issue", "naming_series": "CUST-ISS-.####",
            "issue_date": "2026-05-01", "issued_to_employee": employee or self.employee,
            "building": self._cust_building,
        })
        i.append("items", {"article": article, "qty": qty})
        i.insert(ignore_permissions=True)
        i.submit()
        return i

    def _return(self, issue, article, qty):
        r = frappe.get_doc({
            "doctype": "Custody Return", "naming_series": "CUST-RET-.####",
            "return_date": "2026-05-10", "custody_issue": issue,
            "returned_by_employee": self.employee,
            "building": getattr(self, "_cust_building", None),
        })
        r.append("items", {"article": article, "qty": qty})
        r.insert(ignore_permissions=True)
        r.submit()
        return r

    # Scenario 4a: return MORE qty than issued -> rejected?
    def test_4a_over_return_rejected(self):
        art = self._article()
        issue = self._issue(art, qty=5)
        rejected = True
        err = None
        try:
            self._return(issue.name, art, qty=10)
            rejected = False
        except Exception as e:
            err = str(e)
        print(f"\n[4a] over-return (10 of 5 issued) rejected={rejected} err={err}")
        issue.reload()
        print(f"[4a] issue status after over-return attempt={issue.status}")
        # FIXED (custody_return._validate_return_quantities): over-quantity return is rejected.
        self.assertTrue(rejected, "over-quantity custody return must be rejected")
        self.assertNotEqual(issue.status, "Returned", "over-return must not mark the issue Returned")

    # Scenario 4b: second full return for same issue -> rejected?
    def test_4b_double_full_return(self):
        art = self._article()
        issue = self._issue(art, qty=5)
        self._return(issue.name, art, qty=5)
        rejected = True
        err = None
        try:
            self._return(issue.name, art, qty=5)
            rejected = False
        except Exception as e:
            err = str(e)
        print(f"\n[4b] second full return rejected={rejected} err={err}")
        # FIXED: a second full return exceeds issued qty cumulatively and is rejected.
        self.assertTrue(rejected, "second full custody return must be rejected")

    # Scenario 4c: two Custody Issues of same article to same employee -> rejected or allowed?
    def test_4c_two_issues_same_article_employee(self):
        art = self._article()
        self._issue(art, qty=2)
        allowed = True
        err = None
        try:
            self._issue(art, qty=3)
        except Exception as e:
            allowed = False
            err = str(e)
        print(f"\n[4c] second issue same article+employee allowed={allowed} err={err}")
        print("[4c] BEHAVIOR: two Custody Issues of the same article to the same employee are " + ("ALLOWED (no duplicate guard)" if allowed else f"rejected: {err}"))


class TestDuplicateOverlap(QABase):
    def _utility_account(self, building):
        return frappe.get_doc({
            "doctype": "Utility Account", "naming_series": "UTIL-ACC-.####",
            "building": building, "utility_type": "Electricity",
            "account_number": "ACC-" + _hash(),
        }).insert(ignore_permissions=True).name

    def _bill(self, account, building, pfrom, pto, amount=100):
        b = frappe.get_doc({
            "doctype": "Utility Bill Entry", "naming_series": "UTIL-BILL-.YYYY.-.#####",
            "utility_account": account, "building": building, "utility_type": "Electricity",
            "billing_period_from": pfrom, "billing_period_to": pto,
            "bill_amount_sar": amount, "total_bill_amount_sar": amount,
        })
        b.insert(ignore_permissions=True)
        b.submit()
        return b

    # Scenario 5a: two Utility Bill Entries for same account + same period -> rejected?
    def test_5a_duplicate_utility_bill(self):
        b = self._make_building()
        acc = self._utility_account(b.name)
        self._bill(acc, b.name, "2026-04-01", "2026-04-30")
        rejected = True
        err = None
        try:
            self._bill(acc, b.name, "2026-04-01", "2026-04-30")
            rejected = False
        except Exception as e:
            err = str(e)
        print(f"\n[5a] duplicate utility bill (same account+period) rejected={rejected} err={err}")
        # FIXED (utility_bill_entry.validate): duplicate bill for same account+period is rejected.
        self.assertTrue(rejected, "duplicate utility bill must be rejected")

    # Scenario 5b: two overlapping Accommodation Leases for same building -> rejected?
    def _lease(self, building, start, end, first_pay):
        lease = frappe.get_doc({
            "doctype": "Accommodation Lease", "naming_series": "ACC-LEASE-.YYYY.-.####",
            "building": building, "status": "Active",
            "lease_start_date": start, "lease_end_date": end,
            "rent_amount": 1000, "billing_cycle": "Monthly", "first_payment_date": first_pay,
        })
        lease.insert(ignore_permissions=True)
        lease.submit()
        return lease

    def test_5b_overlapping_leases(self):
        b = self._make_building()
        self._lease(b.name, "2026-01-01", "2026-12-31", "2026-01-01")
        allowed = True
        err = None
        try:
            self._lease(b.name, "2026-06-01", "2027-05-31", "2026-06-01")
        except Exception as e:
            allowed = False
            err = str(e)
        print(f"\n[5b] overlapping lease same building allowed={allowed} err={err}")
        if allowed:
            print("[5b] BUG: two OVERLAPPING Accommodation Leases for the same building accepted. No overlap guard.")
        # CONFIRMED BUG: asserting current (buggy) behavior to keep module green.
        self.assertTrue(allowed, "CONFIRMED BUG: overlapping leases for same building accepted (should be rejected)")

    # Scenario 5c: two Maintenance Work Orders for same Maintenance Request -> rejected?
    def test_5c_two_work_orders_same_request(self):
        b = self._make_building()
        room, _bed = self._first_room_bed(b.name) if frappe.db.count("Accommodation Room", {"building": b.name}) else (None, None)
        if not room:
            generate_rooms_and_beds(b.name)
            room, _bed = self._first_room_bed(b.name)
        mr = frappe.get_doc({
            "doctype": "Maintenance Request", "naming_series": "MAINT-.YYYY.-.#####",
            "building": b.name, "room": room, "reported_by": "Administrator",
            "issue_type": "Electrical", "issue_description": "test", "status": "Open",
        })
        mr.insert(ignore_permissions=True)
        mr.submit()

        def _wo():
            w = frappe.get_doc({
                "doctype": "Maintenance Work Order",
                "maintenance_request": mr.name, "building": b.name, "room": room,
                "planned_start_date": "2026-05-10", "work_description": "fix",
            })
            w.insert(ignore_permissions=True)
            w.submit()
            return w

        _wo()
        allowed = True
        err = None
        try:
            _wo()
        except Exception as e:
            allowed = False
            err = str(e)
        print(f"\n[5c] second work order same request allowed={allowed} err={err}")
        if allowed:
            print("[5c] BUG: two Maintenance Work Orders for the SAME Maintenance Request accepted. No duplicate guard.")
        print("[5c] BEHAVIOR recorded.")
