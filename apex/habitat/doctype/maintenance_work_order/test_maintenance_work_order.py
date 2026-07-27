# Copyright (c) 2026, AFMCO and contributors
"""Maintenance Work Order lifecycle, driven by the roles that actually hold it.

The completion half of this DocType used to be unreachable. ``mark_completed``
demanded ``actual_start_date`` and ``actual_end_date``, neither of which is an
allow_on_submit field, so once the Work Order was submitted no role on the site —
not the Maintenance Technician, not a System Manager — could put a value in them.
The shipped "Mark as Completed" button therefore threw for every Work Order whose
"actual" dates had not been invented before the work began, and the suite missed it
because both existing fixtures pre-filled those dates on the draft and inserted with
``ignore_permissions=True``.

``TestMaintenanceWorkOrderLifecycle`` drives the real thing instead: a System Manager
issues and submits the order, a Maintenance Technician scoped to the building by a
Building User Permission starts it and completes it, and every assertion about who
may do what runs under ``frappe.set_user``. The two closed doors are asserted by name
(``PermissionError`` for the technician, ``UpdateAfterSubmitError`` for the
submit-holder) so the tests keep proving WHY the controlled method has to exist.

Side effects are counted, never merely observed: one Accommodation Ledger memo and
one Maintenance Cost Ledger original per priced item, asserted as a delta, and a
second completion attempt asserted to move the count by zero.
"""

import uuid

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, getdate, today

from apex.tests._helpers import _user, as_user
from apex.tests.factories import make_employee, make_maintenance_request

# [#8evoal]
test_ignore = [
    "Additional Salary",
    "Asset",
    "Asset Movement",
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Item",
    "Payment Entry",
    "Project",
    "Purchase Invoice",
    "Role",
    "Salary Component",
    "Supplier",
    "User",
]


class TestMaintenanceWorkOrder(FrappeTestCase):

    def test_docperm_maintenance_technician(self):
        """Maintenance Technician must have read/write on MWO (no submit/cancel/create/delete)."""
        meta = frappe.get_meta("Maintenance Work Order")
        roles = {p.role: p for p in meta.permissions}
        self.assertIn("Maintenance Technician", roles, "Maintenance Technician perm row is missing")
        p = roles["Maintenance Technician"]
        self.assertEqual(p.read, 1)
        self.assertEqual(p.write, 1)
        self.assertFalse(getattr(p, "submit", 0), "Maintenance Technician must NOT have submit")
        self.assertFalse(getattr(p, "cancel", 0), "Maintenance Technician must NOT have cancel")
        self.assertFalse(getattr(p, "create", 0), "Maintenance Technician must NOT have create")
        self.assertFalse(getattr(p, "delete", 0), "Maintenance Technician must NOT have delete")

    def test_the_actual_dates_are_not_reachable_after_submit(self):
        """The schema fact the controlled completion method exists to work around.

        If either date ever gains allow_on_submit this test fails, and it should: the
        method would stop being the only writer of the completion evidence, and the
        ordering rule it enforces would be bypassable by a plain after-submit save.
        """
        meta = frappe.get_meta("Maintenance Work Order")
        for fieldname in ("actual_start_date", "actual_end_date"):
            with self.subTest(field=fieldname):
                self.assertFalse(
                    meta.get_field(fieldname).allow_on_submit,
                    f"{fieldname} must stay non-allow_on_submit so mark_completed owns it",
                )

    def test_create_valid_work_order(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Work Order",
            "naming_series": "MWO-.YYYY.-.####",
            "maintenance_request": "MAINT-QA-001",
            "work_description": "Fix pipe leak in room 101",
            "planned_start_date": "2026-06-10",
            "planned_end_date": "2026-06-12",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Maintenance Work Order", doc.name, force=True, ignore_permissions=True)

    def test_missing_work_description_raises(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Work Order",
            "naming_series": "MWO-.YYYY.-.####",
            "maintenance_request": "MAINT-QA-001",
            "planned_start_date": "2026-06-10",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_end_date_before_start_raises(self):
        from apex.habitat.doctype.maintenance_work_order.maintenance_work_order import validate

        doc = frappe.get_doc({
            "doctype": "Maintenance Work Order",
            "maintenance_request": "MAINT-QA-001",
            "work_description": "Repair work",
            "planned_start_date": "2026-06-15",
            "planned_end_date": "2026-06-10",
        })
        with self.assertRaises(frappe.ValidationError) as caught:
            validate(doc)
        self.assertIn("Planned End Date", str(caught.exception))

    def test_actual_end_before_actual_start_raises_on_the_draft(self):
        from apex.habitat.doctype.maintenance_work_order.maintenance_work_order import validate

        doc = frappe.get_doc({
            "doctype": "Maintenance Work Order",
            "maintenance_request": "MAINT-QA-001",
            "work_description": "Repair work",
            "planned_start_date": "2026-06-10",
            "planned_end_date": "2026-06-15",
            "actual_start_date": "2026-06-14",
            "actual_end_date": "2026-06-11",
        })
        with self.assertRaises(frappe.ValidationError) as caught:
            validate(doc)
        self.assertIn("Actual End Date", str(caught.exception))


class MaintenanceWorkOrderPersonas(FrappeTestCase):
    """Shared personas and per-method fixtures for the lifecycle suites.

    The users, buildings and Building User Permissions are class-scoped because they
    are read, never mutated. Every Maintenance Request and Work Order is minted per
    METHOD: the rollback is rows-only and fires once for the whole class, so a
    submitted-then-cancelled order left behind by one method would be the fixture the
    next one inherits.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        from apex.setup import create_roles

        create_roles()
        cls.building = cls._building("A271-HOME")
        cls.other_building = cls._building("A271-AWAY")
        cls.room = cls._room(cls.building, "A271-HOME-R1")

        # System Manager is the only role holding create/submit on this DocType today,
        # so it is the issuing persona the shipped DocPerms actually permit.
        cls.manager = _user("a271_manager@example.com", "System Manager")
        cls.tech = cls._scoped_technician("a271_tech@example.com", cls.building)
        cls.away_tech = cls._scoped_technician("a271_away@example.com", cls.other_building)
        # Holds no Maintenance Work Order DocPerm at all — the unauthorized caller.
        cls.bystander = _user("a271_bystander@example.com", "Cleaning Supervisor")

    def tearDown(self):
        # The session user is a process global; the rows-only rollback never restores it,
        # so a method that dies inside a persona would hand the next one that persona.
        frappe.set_user("Administrator")

    @classmethod
    def _building(cls, name):
        if not frappe.db.exists("Building", name):
            frappe.get_doc({
                "doctype": "Building",
                "building_name": name,
                "total_capacity": 4,
            }).insert(ignore_permissions=True, ignore_links=True)
        return name

    @classmethod
    def _room(cls, building, name):
        if not frappe.db.exists("Room", name):
            frappe.get_doc({
                "doctype": "Room",
                "building": building,
                "room_number": name,
                "bed_capacity": 2,
            }).insert(ignore_permissions=True, ignore_links=True)
        return name

    @classmethod
    def _scoped_technician(cls, email, building):
        """A Maintenance Technician the building-scope hook will actually admit.

        ``building_scoped_has_permission`` denies every doc whose building is not in
        the user's Building User Permissions, so a technician without one is inert on
        this DocType regardless of the DocPerm row.
        """
        user = _user(email, "Maintenance Technician")
        existing = frappe.db.exists(
            "User Permission", {"user": user, "allow": "Building", "for_value": building}
        )
        if not existing:
            perm = frappe.get_doc({
                "doctype": "User Permission",
                "user": user,
                "allow": "Building",
                "for_value": building,
            }).insert(ignore_permissions=True)
            cls.addClassCleanup(
                frappe.delete_doc, "User Permission", perm.name,
                force=True, ignore_permissions=True,
            )
        return user

    def _draft_work_order(self, cost=25):
        """A DRAFT Work Order created BY THE MANAGER, no ignore_permissions anywhere on
        the Work Order path.

        Cleanup is registered as soon as the row exists, so a method that raises
        mid-lifecycle still hands the next one a clean table.
        """
        mr = make_maintenance_request(self.building, self.room)
        self.addCleanup(self._drop_request, mr.name)
        with as_user(self.manager):
            wo = frappe.get_doc({
                "doctype": "Maintenance Work Order",
                "naming_series": "MWO-.YYYY.-.####",
                "maintenance_request": mr.name,
                "work_description": f"Reseat the valve {uuid.uuid4().hex[:12]}",
                "planned_start_date": today(),
                "planned_end_date": add_days(today(), 2),
                "procurement_items": [
                    {"item_description": "Tap washer", "quantity": 1, "estimated_cost": cost}
                ],
            })
            wo.insert()
            self.addCleanup(self._drop_work_order, wo.name)
        return mr, wo

    def _issue_work_order(self, cost=25):
        """The draft above, submitted by the manager. Returns the reloaded document."""
        mr, wo = self._draft_work_order(cost=cost)
        with as_user(self.manager):
            wo.submit()
        wo.reload()
        return mr, wo

    def _drop_work_order(self, name):
        frappe.set_user("Administrator")
        if not frappe.db.exists("Maintenance Work Order", name):
            return
        doc = frappe.get_doc("Maintenance Work Order", name)
        if doc.docstatus == 1:
            doc.cancellation_reason = doc.cancellation_reason or "cleanup"
            doc.cancel()
        for row in self._accommodation_rows(name):
            frappe.delete_doc("Accommodation Ledger", row, force=True, ignore_permissions=True)
        for row in self._cost_rows(name):
            frappe.delete_doc("Maintenance Cost Ledger", row, force=True, ignore_permissions=True)
        frappe.delete_doc("Maintenance Work Order", name, force=True, ignore_permissions=True)

    def _drop_request(self, name):
        frappe.set_user("Administrator")
        if not frappe.db.exists("Maintenance Request", name):
            return
        doc = frappe.get_doc("Maintenance Request", name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("Maintenance Request", name, force=True, ignore_permissions=True)

    @staticmethod
    def _accommodation_rows(wo_name, **extra):
        filters = {"source_doctype": "Maintenance Work Order", "source_name": wo_name}
        filters.update(extra)
        return frappe.get_all("Accommodation Ledger", filters=filters, pluck="name")

    @staticmethod
    def _cost_rows(wo_name, **extra):
        filters = {"source_doctype": "Maintenance Work Order", "source_name": wo_name}
        filters.update(extra)
        return frappe.get_all("Maintenance Cost Ledger", filters=filters, pluck="name")

    def _side_effect_counts(self, wo_name):
        """(accommodation memo rows, cost ledger rows) for this Work Order."""
        return len(self._accommodation_rows(wo_name)), len(self._cost_rows(wo_name))


class TestMaintenanceWorkOrderLifecycle(MaintenanceWorkOrderPersonas):
    """Create, assign, start, complete — each step taken by a role that can reach it."""

    def test_the_manager_issues_and_the_technician_starts(self):
        from apex.habitat.doctype.maintenance_work_order.maintenance_work_order import start_work

        _mr, wo = self._issue_work_order()
        self.assertEqual(wo.docstatus, 1)
        self.assertEqual(wo.status, "Planned", "on_submit must park the order at Planned")
        self.assertFalse(wo.actual_start_date, "an unstarted order carries no actual start")

        with as_user(self.tech):
            start_work(wo.name)

        wo.reload()
        self.assertEqual(wo.status, "In Progress")
        self.assertEqual(
            getdate(wo.actual_start_date), getdate(today()),
            "start_work must stamp the actual start; it is the technician's only route "
            "to that field once the order is submitted",
        )

    def test_the_manager_assigns_the_crew_and_submit_freezes_it(self):
        """``assigned_to`` is a draft-time field: the issuing manager names the crew, and
        the field is not allow_on_submit, so a submitted order cannot be quietly
        reassigned to somebody else's technician.
        """
        employee = make_employee("A271 Technician")
        _mr, draft = self._draft_work_order()
        with as_user(self.manager):
            doc = frappe.get_doc("Maintenance Work Order", draft.name)
            doc.assigned_to = employee.name
            doc.save()
            doc.submit()

        self.assertEqual(
            frappe.db.get_value("Maintenance Work Order", draft.name, "assigned_to"),
            employee.name,
        )
        self.assertFalse(
            frappe.get_meta("Maintenance Work Order").get_field("assigned_to").allow_on_submit,
            "assigned_to is frozen at submit; reassignment is an amend, not a quiet edit",
        )

    def test_the_technician_cannot_write_the_evidence_through_the_form(self):
        """The defect this card exists for, asserted from both sides of the door.

        The technician is refused because saving a submitted document is
        ``update_after_submit`` and Frappe gates that on the SUBMIT permission, which
        the DocPerm withholds. The manager holds submit and is still refused, because
        the date is not allow_on_submit. No role on the site can reach the field.
        """
        from apex.habitat.doctype.maintenance_work_order.maintenance_work_order import start_work

        _mr, wo = self._issue_work_order()
        with as_user(self.tech):
            start_work(wo.name)

        before = frappe.db.get_value("Maintenance Work Order", wo.name, "actual_end_date")

        with as_user(self.tech):
            attempt = frappe.get_doc("Maintenance Work Order", wo.name)
            attempt.actual_end_date = add_days(today(), 1)
            with self.assertRaises(frappe.PermissionError):
                attempt.save()

        with as_user(self.manager):
            attempt = frappe.get_doc("Maintenance Work Order", wo.name)
            attempt.actual_end_date = add_days(today(), 1)
            with self.assertRaises(frappe.UpdateAfterSubmitError):
                attempt.save()

        self.assertEqual(
            frappe.db.get_value("Maintenance Work Order", wo.name, "actual_end_date"),
            before,
            "a refused save must leave the stored date untouched",
        )

    def test_the_technician_records_evidence_and_completes(self):
        from apex.habitat.doctype.maintenance_work_order.maintenance_work_order import (
            mark_completed,
            start_work,
        )

        _mr, wo = self._issue_work_order()
        with as_user(self.tech):
            start_work(wo.name)
            mark_completed(
                wo.name,
                actual_end_date=add_days(today(), 1),
                completion_photo="/files/a271-done.png",
                completion_notes="Valve reseated and pressure tested",
            )

        wo.reload()
        self.assertEqual(wo.docstatus, 1, "completion is a status move, never a docstatus move")
        self.assertEqual(wo.status, "Completed")
        self.assertEqual(wo.completion_photo, "/files/a271-done.png")
        self.assertEqual(wo.completion_notes, "Valve reseated and pressure tested")
        self.assertEqual(getdate(wo.actual_end_date), getdate(add_days(today(), 1)))
        self.assertLessEqual(
            getdate(wo.actual_start_date), getdate(wo.actual_end_date),
            "the recorded actual dates must stay ordered",
        )

    def test_completion_is_refused_before_the_work_is_started(self):
        from apex.habitat.doctype.maintenance_work_order.maintenance_work_order import (
            mark_completed,
        )

        _mr, wo = self._issue_work_order()
        before = self._side_effect_counts(wo.name)

        with as_user(self.tech):
            with self.assertRaises(frappe.ValidationError) as caught:
                mark_completed(
                    wo.name,
                    actual_end_date=today(),
                    completion_photo="/files/a271-jumped.png",
                )
        self.assertIn("Start the work first", str(caught.exception))

        wo.reload()
        self.assertEqual(wo.status, "Planned", "a refused completion must not move the status")
        self.assertEqual(
            self._side_effect_counts(wo.name), before,
            "a refused completion must post no ledger row of either kind",
        )

    def test_out_of_order_actual_dates_are_refused_after_submit(self):
        """validate() never runs on the after-submit path, so the ordering rule has to
        live in the method that writes the dates. Prove it does, and that the refusal
        costs the order neither its status nor a stray ledger row.
        """
        from apex.habitat.doctype.maintenance_work_order.maintenance_work_order import (
            mark_completed,
            start_work,
        )

        _mr, wo = self._issue_work_order()
        with as_user(self.tech):
            start_work(wo.name)
        before = self._side_effect_counts(wo.name)

        with as_user(self.tech):
            with self.assertRaises(frappe.ValidationError) as caught:
                mark_completed(
                    wo.name,
                    actual_end_date=add_days(today(), -3),
                    completion_photo="/files/a271-backdated.png",
                )
        self.assertIn("Actual End Date", str(caught.exception))

        wo.reload()
        self.assertEqual(wo.status, "In Progress")
        self.assertEqual(self._side_effect_counts(wo.name), before)

    def test_completion_without_a_photo_is_refused(self):
        from apex.habitat.doctype.maintenance_work_order.maintenance_work_order import (
            mark_completed,
            start_work,
        )

        _mr, wo = self._issue_work_order()
        with as_user(self.tech):
            start_work(wo.name)
            with self.assertRaises(frappe.ValidationError) as caught:
                mark_completed(wo.name, actual_end_date=today())
        self.assertIn("completion photo", str(caught.exception))

    def test_an_unauthorized_user_cannot_start_or_complete(self):
        from apex.habitat.doctype.maintenance_work_order.maintenance_work_order import (
            mark_completed,
            start_work,
        )

        _mr, wo = self._issue_work_order()
        with as_user(self.bystander):
            with self.assertRaises(frappe.PermissionError):
                start_work(wo.name)
            with self.assertRaises(frappe.PermissionError):
                mark_completed(wo.name, actual_end_date=today())

        wo.reload()
        self.assertEqual(wo.status, "Planned")

    def test_a_technician_from_another_building_is_refused(self):
        from apex.habitat.doctype.maintenance_work_order.maintenance_work_order import start_work

        _mr, wo = self._issue_work_order()
        with as_user(self.away_tech):
            with self.assertRaises(frappe.PermissionError):
                start_work(wo.name)

        wo.reload()
        self.assertEqual(wo.status, "Planned")

    def test_the_technician_cannot_submit_a_draft(self):
        _mr, draft = self._draft_work_order()
        with as_user(self.tech):
            attempt = frappe.get_doc("Maintenance Work Order", draft.name)
            with self.assertRaises(frappe.PermissionError):
                attempt.submit()

        self.assertEqual(
            frappe.db.get_value("Maintenance Work Order", draft.name, "docstatus"), 0,
            "the order authorising the work stays with the issuer, not the technician",
        )

    def test_the_technician_cannot_cancel(self):
        _mr, wo = self._issue_work_order()
        with as_user(self.tech):
            attempt = frappe.get_doc("Maintenance Work Order", wo.name)
            attempt.cancellation_reason = "not mine to cancel"
            with self.assertRaises(frappe.PermissionError):
                attempt.cancel()

        wo.reload()
        self.assertEqual(wo.docstatus, 1, "the order must survive the refused cancel")


class TestMaintenanceWorkOrderSideEffects(MaintenanceWorkOrderPersonas):
    """Completion posts its memos exactly once; cancellation reverses without erasing."""

    def test_completion_posts_each_side_effect_exactly_once(self):
        from apex.habitat.doctype.maintenance_work_order.maintenance_work_order import (
            mark_completed,
            start_work,
        )

        _mr, wo = self._issue_work_order(cost=25)
        with as_user(self.tech):
            start_work(wo.name)

        before_memo, before_cost = self._side_effect_counts(wo.name)
        self.assertEqual((before_memo, before_cost), (0, 0), "nothing is posted before completion")

        with as_user(self.tech):
            mark_completed(
                wo.name, actual_end_date=today(), completion_photo="/files/a271-once.png"
            )

        after_memo, after_cost = self._side_effect_counts(wo.name)
        self.assertEqual(after_memo - before_memo, 1, "exactly one Accommodation Ledger memo")
        self.assertEqual(after_cost - before_cost, 1, "exactly one Maintenance Cost Ledger row")

    def test_a_second_completion_attempt_posts_nothing(self):
        from apex.habitat.doctype.maintenance_work_order.maintenance_work_order import (
            mark_completed,
            start_work,
        )

        _mr, wo = self._issue_work_order(cost=25)
        with as_user(self.tech):
            start_work(wo.name)
            mark_completed(
                wo.name, actual_end_date=today(), completion_photo="/files/a271-twice.png"
            )
        after_first = self._side_effect_counts(wo.name)

        with as_user(self.tech):
            with self.assertRaises(frappe.ValidationError) as caught:
                mark_completed(wo.name, actual_end_date=today())
        self.assertIn("already Completed", str(caught.exception))

        self.assertEqual(
            self._side_effect_counts(wo.name), after_first,
            "a rejected re-completion must move neither ledger count",
        )

    def test_cancel_reverses_without_erasing_the_originals(self):
        """Assert what SURVIVES: the original rows keep their identity, a mirror row is
        added beside them, and the pair nets to zero. A cancel that merely 'succeeded'
        is also what a delete looks like from the outside.
        """
        from apex.habitat.doctype.maintenance_work_order.maintenance_work_order import (
            mark_completed,
            start_work,
        )

        mr, wo = self._issue_work_order(cost=25)
        with as_user(self.tech):
            start_work(wo.name)
            mark_completed(
                wo.name, actual_end_date=today(), completion_photo="/files/a271-cancel.png"
            )

        memo_originals = set(self._accommodation_rows(wo.name, reversal_of=["is", "not set"]))
        cost_originals = set(self._cost_rows(wo.name, reversal_of=["is", "not set"]))
        self.assertEqual(len(memo_originals), 1)
        self.assertEqual(len(cost_originals), 1)
        self.assertEqual(frappe.db.get_value("Maintenance Request", mr.name, "status"), "Closed")

        with as_user(self.manager):
            doc = frappe.get_doc("Maintenance Work Order", wo.name)
            doc.cancellation_reason = "Duplicate work order"
            doc.cancel()

        self.assertTrue(
            memo_originals.issubset(set(self._accommodation_rows(wo.name))),
            "the original Accommodation Ledger memo must still exist after cancel",
        )
        self.assertTrue(
            cost_originals.issubset(set(self._cost_rows(wo.name))),
            "the original Maintenance Cost Ledger row must still exist after cancel",
        )
        self.assertEqual(
            len(self._accommodation_rows(wo.name)), 2, "one reversal beside the original"
        )
        self.assertEqual(len(self._cost_rows(wo.name)), 2, "one reversal beside the original")

        memo_total = sum(
            flt(r.total_site_cost)
            for r in frappe.get_all(
                "Accommodation Ledger",
                filters={"source_doctype": "Maintenance Work Order", "source_name": wo.name},
                fields=["total_site_cost"],
            )
        )
        cost_total = sum(
            flt(r.amount)
            for r in frappe.get_all(
                "Maintenance Cost Ledger",
                filters={"source_doctype": "Maintenance Work Order", "source_name": wo.name},
                fields=["amount"],
            )
        )
        self.assertEqual(memo_total, 0, "the reversed accommodation memo must net to zero")
        self.assertEqual(cost_total, 0, "the reversed cost ledger must net to zero")
        self.assertEqual(
            frappe.db.get_value("Maintenance Request", mr.name, "status"), "Open",
            "cancel must release the request off Closed",
        )

    def test_cancel_requires_a_reason(self):
        _mr, wo = self._issue_work_order()
        with as_user(self.manager):
            doc = frappe.get_doc("Maintenance Work Order", wo.name)
            with self.assertRaises(frappe.ValidationError) as caught:
                doc.cancel()
        self.assertIn("Cancellation Reason", str(caught.exception))

        wo.reload()
        self.assertEqual(wo.docstatus, 1)
