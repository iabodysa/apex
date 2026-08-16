# Copyright (c) 2026, AFMCO and contributors
"""Direct coverage for ``apex.habitat.utils.arrival_slips``.

The masthead builder (``slip_context``) and its supporting helpers
(``slip_company``, ``slip_direction``, ``party_type_label``) take plain values and
return values or read one Single/user default, so they are exercisable without the
Arrivals Desk API in the loop. The XSS regression suite
(``habitat/api/test_arrivals_slip_xss.py``) already pins that every field on
``ARRIVAL_SLIP_TEMPLATE`` is escaped; this file pins the CONTRACT between
``slip_context``'s output keys and what the template reads: an Employee slip
renders the worker's name, and a Temporary Worker slip renders the passport
number the same way ``arrivals_desk.get_arrival_slip`` assembles it.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.party_link import PARTY_EMPLOYEE, PARTY_TEMPORARY_WORKER
from apex.habitat.utils import arrival_slips
from apex.habitat.utils.arrival_slips import ARRIVAL_SLIP_TEMPLATE
from apex.tests import factories


def _tag() -> str:
    """A collision-free identifier suffix, matching the suite-wide entropy floor."""
    return frappe.generate_hash(length=12)


class TestPartyTypeLabel(FrappeTestCase):
    """Pure lookup — no database involved."""

    def test_known_party_types_get_a_translated_label(self):
        """The two party types the desk supports map to their display labels."""
        self.assertEqual(arrival_slips.party_type_label(PARTY_EMPLOYEE), "Employee")
        self.assertEqual(arrival_slips.party_type_label(PARTY_TEMPORARY_WORKER), "Temporary Worker")

    def test_an_unknown_or_missing_party_type_falls_back_to_itself(self):
        """A party type outside the two known ones is returned as-is; a blank one
        is an empty string, never ``None``."""
        self.assertEqual(arrival_slips.party_type_label("Something Else"), "Something Else")
        self.assertEqual(arrival_slips.party_type_label(None), "")


class TestSlipDirectionAndCompany(FrappeTestCase):
    """Reads the boot language and the shared Habitat company resolver."""

    def test_slip_direction_follows_the_active_language(self):
        """An Arabic session renders right-to-left; anything else left-to-right."""
        original_lang = frappe.local.lang
        try:
            frappe.local.lang = "ar"
            self.assertEqual(arrival_slips.slip_direction(), "rtl")
            frappe.local.lang = "en"
            self.assertEqual(arrival_slips.slip_direction(), "ltr")
        finally:
            frappe.local.lang = original_lang

    def test_slip_company_matches_the_shared_habitat_resolver(self):
        """``slip_company`` is a thin wrapper over the shared resolver, scoped to
        Habitat, never blank when no company is configured."""
        from apex.apex_core.utils.company import resolve_company

        self.assertEqual(arrival_slips.slip_company(), resolve_company("Habitat") or "")


class TestSlipContext(FrappeTestCase):
    """The masthead every slip carries."""

    def test_masthead_carries_worker_and_party_type_fields(self):
        """Given a party type, the masthead carries both the raw type and its label."""
        ctx = arrival_slips.slip_context("Jane Doe", PARTY_EMPLOYEE)
        self.assertEqual(ctx["worker_name"], "Jane Doe")
        self.assertEqual(ctx["party_type"], PARTY_EMPLOYEE)
        self.assertEqual(ctx["party_type_label"], "Employee")
        self.assertIn(ctx["dir"], ("ltr", "rtl"))
        self.assertIn("company", ctx)
        self.assertIn("today", ctx)

    def test_party_type_is_omitted_when_the_slip_has_no_party(self):
        """The custody-handover slip identifies its worker by a document reference,
        not a party, so ``slip_context`` must not invent one."""
        ctx = arrival_slips.slip_context("Some Reference")
        self.assertNotIn("party_type", ctx)
        self.assertNotIn("party_type_label", ctx)


class TestArrivalSlipRendering(FrappeTestCase):
    """Renders ``ARRIVAL_SLIP_TEMPLATE`` the way ``arrivals_desk.get_arrival_slip``
    assembles it, per party type."""

    def setUp(self):
        """Ensures the shared test company exists before any Employee is built."""
        factories.make_company()

    def _base_ctx(self, worker_name, party_type):
        ctx = arrival_slips.slip_context(worker_name, party_type)
        ctx.update(
            {
                "building": "",
                "bed": "",
                "project": "",
                "check_in_date": "",
                "designation": None,
                "passport_number": None,
                "iqama_number": None,
                "nationality": None,
                "qr": None,
            }
        )
        return ctx

    def test_an_employee_slip_renders_the_employees_name(self):
        """A slip for ``party_type == 'Employee'`` renders the employee's name."""
        employee = factories.make_employee(name=f"Slip Employee {_tag()}")
        worker_name = frappe.db.get_value("Employee", employee.name, "employee_name")

        ctx = self._base_ctx(worker_name, PARTY_EMPLOYEE)
        html = frappe.render_template(ARRIVAL_SLIP_TEMPLATE, ctx)

        self.assertIn(worker_name, html)
        self.assertIn("Employee", html)

    def test_a_temporary_worker_slip_renders_the_passport_number(self):
        """A Temporary Worker slip renders the passport number."""
        suffix = _tag()
        temporary_worker = frappe.get_doc(
            {
                "doctype": "Temporary Worker",
                "worker_name": f"Slip Temporary Worker {suffix}",
                "passport_number": f"P{suffix.upper()}",
                "arrival_date": frappe.utils.today(),
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        row = frappe.db.get_value(
            "Temporary Worker", temporary_worker.name,
            ["worker_name", "passport_number"], as_dict=True,
        )

        ctx = self._base_ctx(row.worker_name, PARTY_TEMPORARY_WORKER)
        ctx["passport_number"] = row.passport_number
        html = frappe.render_template(ARRIVAL_SLIP_TEMPLATE, ctx)

        self.assertIn(row.passport_number, html)
        self.assertIn("Temporary Worker", html)

    def test_an_employee_slip_does_not_render_a_passport_row(self):
        """The passport row is conditional; an Employee slip carries none."""
        ctx = self._base_ctx("Jane Doe", PARTY_EMPLOYEE)
        html = frappe.render_template(ARRIVAL_SLIP_TEMPLATE, ctx)
        self.assertNotIn("Passport", html)
