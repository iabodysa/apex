# Copyright (c) 2026, AFMCO and contributors
# [#plvx64]

import frappe
from apex.tests.factories import ApexHabitatTestCase
from apex.habitat.doctype.building.building import (
    generate_rooms_and_beds,
)


def _hash(n=12):
    return frappe.generate_hash(length=n).upper()


class QABase(ApexHabitatTestCase):
    def setUp(self):
        # [#ianq9k]
        self.company = frappe.db.get_value("Company", {}, order_by="creation asc") or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Company",
            "default_currency": "SAR", "country": "Saudi Arabia",
        }).insert(ignore_permissions=True).name
        # [#bkqjhk]
        self.cost_center = frappe.db.get_value(
            "Cost Center", {"is_group": 0, "company": self.company}
        )
        self.project = frappe.db.get_value("Project", {}) or frappe.get_doc({
            "doctype": "Project", "project_name": "Test Project", "company": self.company,
        }).insert(ignore_permissions=True).name
        # [#91r2jb]
        self.employee = frappe.get_doc({
            "doctype": "Employee", "first_name": "QA Emp " + _hash(),
            "company": self.company, "gender": "Male",
            "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01",
        }).insert(ignore_permissions=True).name
        self.site = frappe.get_doc({
            "doctype": "Site", "site_name": _hash(12),
        }).insert(ignore_permissions=True)

    def _make_building(self, room_count=3, room_type="Standard", capacity=2, total_capacity=50):
        abbr = "B" + _hash(3)
        b = frappe.get_doc({
            "doctype": "Building",
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
        room = frappe.get_all("Room", {"building": building}, pluck="name")[0]
        bed = frappe.get_all("Bed", {"room": room}, pluck="name")[0]
        return room, bed

    def _assignment(self, building, room, bed, employee=None):
        a = frappe.get_doc({
            "doctype": "Housing Assignment",
            "employee": employee or self.employee, "project": self.project,
            "cost_center": self.cost_center, "building": building,
            "room": room, "bed": bed, "check_in_date": "2026-05-01",
            "assignment_type": "New Assignment",
        })
        a.insert(ignore_permissions=True)
        a.submit()
        return a


class TestRoomGenerator(QABase):
    # [#jyrwfb]
    def test_1a_rerun_same_plan_no_duplicates(self):
        b = self._make_building(room_count=3)
        generate_rooms_and_beds(b.name)
        before = frappe.db.count("Room", {"building": b.name})
        res = generate_rooms_and_beds(b.name)
        after = frappe.db.count("Room", {"building": b.name})
        print(f"\n[1a] rooms before={before} after={after} created={res['created_rooms']} skipped={res['skipped_rooms']}")
        self.assertEqual(after, before, "BUG: re-run created duplicate rooms")
        self.assertEqual(res["created_rooms"], 0)

    # [#od7oek]
    def test_1b_change_room_type_updates_existing(self):
        b = self._make_building(room_count=3, room_type="Standard")
        generate_rooms_and_beds(b.name)
        room = frappe.get_all("Room", {"building": b.name}, pluck="name")[0]

        b.reload()
        b.floor_plan[0].room_type = "Supervisor"
        b.save(ignore_permissions=True)
        res = generate_rooms_and_beds(b.name)
        type_after = frappe.db.get_value("Room", room, "room_type")
        print(f"\n[1b] room_type after={type_after} updated={res.get('updated_rooms')} created={res.get('created_rooms')}")
        self.assertEqual(type_after, "Supervisor", "existing room type must update to match the plan")
        self.assertGreaterEqual(res.get("updated_rooms", 0), 1)
        self.assertEqual(res.get("created_rooms"), 0)

    # [#a0gtk7]
    def test_1c_increase_room_count_requires_confirmation(self):
        b = self._make_building(room_count=3)
        generate_rooms_and_beds(b.name)
        before = frappe.db.count("Room", {"building": b.name})

        b.reload()
        b.floor_plan[0].room_count = 5
        b.save(ignore_permissions=True)

        # [#dz2rbh]
        res = generate_rooms_and_beds(b.name)
        mid = frappe.db.count("Room", {"building": b.name})
        print(f"\n[1c] no-confirm before={before} after={mid} created={res.get('created_rooms')} pending={res.get('pending_new_rooms')} needs_confirmation={res.get('needs_confirmation')}")
        self.assertTrue(res.get("needs_confirmation"), "new rooms must require confirmation")
        self.assertEqual(res.get("created_rooms"), 0)
        self.assertEqual(mid, before, "no rooms may be created without confirmation")
        self.assertEqual(res.get("pending_new_rooms"), 2)

        # [#76jxz7]
        res2 = generate_rooms_and_beds(b.name, confirm_new_rooms=1)
        after = frappe.db.count("Room", {"building": b.name})
        print(f"[1c] confirmed after={after} created={res2.get('created_rooms')}")
        self.assertEqual(res2.get("created_rooms"), 2)
        self.assertEqual(after, before + 2)


class TestCheckout(QABase):
    # [#jvfrqh]
    def test_2_double_checkout_rejected(self):
        b = self._make_building()
        generate_rooms_and_beds(b.name)
        room, bed = self._first_room_bed(b.name)
        a = self._assignment(b.name, room, bed)

        c1 = frappe.get_doc({
            "doctype": "Housing Checkout", "assignment": a.name,
            "checkout_date": "2026-05-21", "checkout_reason": "Final Exit",
        })
        c1.insert(ignore_permissions=True)
        c1.submit()

        c2 = frappe.get_doc({
            "doctype": "Housing Checkout", "assignment": a.name,
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
    # [#pmjdgz]
    def test_3_cancelled_assignment_allows_recreate(self):
        b = self._make_building()
        generate_rooms_and_beds(b.name)
        room, bed = self._first_room_bed(b.name)

        a1 = self._assignment(b.name, room, bed)
        a1.cancel()
        print(f"\n[3] a1 docstatus after cancel={a1.docstatus}, bed status={frappe.db.get_value('Bed', bed, 'status')}")

        allowed = True
        err = None
        try:
            self._assignment(b.name, room, bed)
        except Exception as e:
            allowed = False
            err = str(e)
        print(f"[3] re-create after cancel allowed={allowed} err={err}")
        self.assertTrue(allowed, f"BUG: cancelled assignment wrongly blocked re-create: {err}")

    # [#2hduyn]
    def test_3b_recheckout_after_checkout_cancel(self):
        b = self._make_building()
        generate_rooms_and_beds(b.name)
        room, bed = self._first_room_bed(b.name)
        a = self._assignment(b.name, room, bed)
        self._assignment_a = a

        c1 = frappe.get_doc({
            "doctype": "Housing Checkout", "assignment": a.name,
            "checkout_date": "2026-05-21", "checkout_reason": "Final Exit",
        })
        c1.insert(ignore_permissions=True)
        c1.submit()
        c1.reload()
        c1.cancellation_reason = "QA test"
        c1.cancel()
        a.reload()
        print(f"\n[3b] after checkout cancel: assignment.check_out_date={a.check_out_date}, bed={frappe.db.get_value('Bed', bed, 'status')}")

        c2 = frappe.get_doc({
            "doctype": "Housing Checkout", "assignment": a.name,
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
        # [#ngagme]
        from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
            post_stock_entry,
        )
        post_stock_entry(item_type="Custody Article", item=article, qty=qty,
                         building=self._cust_building, voucher_type="Opening Stock",
                         voucher_no="OPEN-" + _hash())
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

    # [#fee3o1]
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
        # [#3g5qhp]
        self.assertTrue(rejected, "over-quantity custody return must be rejected")
        self.assertNotEqual(issue.status, "Returned", "over-return must not mark the issue Returned")

    # [#r2oxpn]
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
        # [#33yq43]
        self.assertTrue(rejected, "second full custody return must be rejected")

    # [#ohimc7]
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
            "bill_amount": amount, "total_bill_amount": amount,
        })
        b.insert(ignore_permissions=True)
        b.submit()
        return b

    # [#pcy62y]
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
        # [#ld1x29]
        self.assertTrue(rejected, "duplicate utility bill must be rejected")

    # [#gxkhtt]
    def _lease(self, building, start, end, first_pay):
        # [#9omige]
        from frappe.model.workflow import apply_workflow
        lease = frappe.get_doc({
            "doctype": "Lease", "naming_series": "ACC-LEASE-.YYYY.-.####",
            "building": building, "company": self.company, "status": "Draft",
            "lease_start_date": start, "lease_end_date": end,
            "rent_amount": 1000, "billing_cycle": "Monthly", "first_payment_date": first_pay,
        })
        lease.insert(ignore_permissions=True)
        apply_workflow(lease, "Submit for Approval")
        apply_workflow(lease, "Approve")
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
        # [#1mwpx6]
        self.assertFalse(allowed, "overlapping leases for the same building must be rejected")

    # [#rndih9]
    def test_5c_two_work_orders_same_request(self):
        b = self._make_building()
        room, _bed = self._first_room_bed(b.name) if frappe.db.count("Room", {"building": b.name}) else (None, None)
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
        # [#o0lect]
        self.assertFalse(allowed, "a second Work Order for the same Maintenance Request must be rejected")
