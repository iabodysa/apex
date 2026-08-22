# Copyright (c) 2026, afmcoltd
"""What a Safety Incident guarantees, asserted against the DocType itself.

Patterned on frappe's own document-validation tests (``frappe/tests/test_document.py``,
``test_mandatory`` / ``test_validate``). ``validate`` is a genuine class method (the
controller's own docstring notes it needs no ``hooks.py`` wiring), so every case here goes
through the real lifecycle call — ``insert()`` / ``save()``.

Guarantees: ``reported_by`` defaults to the current user when not given; closing an
incident (status Closed) without Resolution Notes is refused, since an auditor reads the
printed report, not the version history, and an incident closed with no notes and no date
cannot answer how long the site carried the hazard; closing stamps ``closed_on``/
``closed_by`` once, and reopening clears both so a reopened incident never prints a
closure it no longer has.
"""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestSafetyIncident(FrappeTestCase):
    def test_reported_by_defaults_to_the_current_user(self):
        """An incident with nobody named as the reporter would be unattributable in the
        printed report."""
        incident = frappe.copy_doc(frappe.get_test_records("Safety Incident")[0])
        self.assertFalse(incident.reported_by)

        incident.insert()

        self.assertEqual(incident.reported_by, frappe.session.user)

    def test_closing_without_resolution_notes_is_refused(self):
        """A Closed incident with no record of how it was resolved leaves an auditor
        nothing to read."""
        incident = frappe.copy_doc(frappe.get_test_records("Safety Incident")[0])
        incident.status = "Closed"

        with self.assertRaisesRegex(
            frappe.ValidationError, "Resolution Notes are required"
        ):
            incident.insert()

    def test_closing_with_resolution_notes_stamps_closed_on_and_closed_by(self):
        """The acceptance counterpart — a stated resolution must still let the incident
        close, and the closure date/closer are stamped automatically so time-to-close is
        on the record without anyone filling it in by hand."""
        incident = frappe.copy_doc(frappe.get_test_records("Safety Incident")[0])
        incident.status = "Closed"
        incident.resolution_notes = "_T-Wet floor sign added and area mopped"

        incident.insert()

        self.assertEqual(incident.closed_on, frappe.utils.nowdate())
        self.assertEqual(incident.closed_by, frappe.session.user)

    def test_reopening_a_closed_incident_clears_the_closure_stamp(self):
        """A reopened incident must never go on printing a closure it no longer has."""
        incident = frappe.copy_doc(frappe.get_test_records("Safety Incident")[0])
        incident.status = "Closed"
        incident.resolution_notes = "_T-Wet floor sign added and area mopped"
        incident.insert()
        self.assertTrue(incident.closed_on)

        incident.status = "Under Investigation"
        incident.save()

        self.assertFalse(incident.closed_on)
        self.assertFalse(incident.closed_by)
