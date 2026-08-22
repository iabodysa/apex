# Copyright (c) 2026, afmcoltd
"""What Maintenance Request guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is the module-level
``validate`` wired in ``hooks.py``, plus the whitelisted lifecycle actions
``close_request`` and ``reopen_request`` and the mapper ``make_work_order``. A new
request always opens as "Open" and names its reporter; status can only move through
those actions afterward, never a raw field edit — the guard fires on any direct change,
which is also how a "Resolved" status set by an external writer (a Work Order
completion, via ``db_set``) still gets its resolution-notes requirement enforced on the
request's next ordinary save. ``make_work_order`` never copies "status" across, since
the source's "Open" would silently overwrite the mapped Work Order's own default.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.maintenance_request.maintenance_request import (
    close_request,
    make_work_order,
    reopen_request,
)

test_dependencies = ["Building", "Room"]


def _new_request(**overrides):
    record = frappe.copy_doc(frappe.get_test_records("Maintenance Request")[0])
    for field, value in overrides.items():
        record.set(field, value)
    record.insert()
    return record


class TestMaintenanceRequest(FrappeTestCase):
    def test_a_new_request_opens_as_open_and_names_its_reporter(self):
        """A request nobody named as reporter, or one that opened as anything but Open,
        cannot be triaged."""
        record = frappe.copy_doc(frappe.get_test_records("Maintenance Request")[0])
        record.reported_by = None
        record.status = "Resolved"
        record.insert()

        self.assertEqual(record.status, "Open")
        self.assertEqual(record.reported_by, frappe.session.user)

    def test_changing_status_by_a_direct_edit_is_refused(self):
        """Status moves only through the request's own actions, never a raw field edit."""
        record = _new_request()

        record.status = "Resolved"
        with self.assertRaisesRegex(frappe.PermissionError, "Maintenance Request actions"):
            record.save()

    def test_a_resolved_status_set_underneath_the_request_still_needs_notes_on_save(self):
        """An externally-set Resolved status (a Work Order completion, via db_set) is not
        exempt from the notes requirement the next time this record is saved."""
        record = _new_request()
        record.db_set("status", "Resolved")
        record.reload()

        record.notes = None
        with self.assertRaisesRegex(frappe.ValidationError, "Resolution Notes are required"):
            record.save()

        record.reload()
        record.resolution_notes = "Filter replaced and unit tested."
        record.save()
        self.assertEqual(record.status, "Resolved")

    def test_a_negative_repair_cost_is_refused(self):
        """A negative cost cannot describe money actually spent on a repair."""
        record = _new_request()
        record.cost_of_repair = -100

        with self.assertRaisesRegex(frappe.ValidationError, "cannot be negative"):
            record.save()

    def test_make_work_order_maps_the_request_but_never_its_status(self):
        """The mapped Work Order must carry this request's link, not its "Open" status."""
        record = _new_request()

        mapped = make_work_order(record.name)

        self.assertEqual(mapped.maintenance_request, record.name)
        self.assertEqual(mapped.building, record.building)
        self.assertEqual(mapped.status, "Planned")

    def test_close_request_is_refused_on_a_draft_or_a_still_open_submitted_request(self):
        """Closing needs both a submitted request and a Resolved status."""
        draft = _new_request()
        with self.assertRaisesRegex(frappe.ValidationError, "Only submitted"):
            close_request(draft.name)

        draft.submit()
        with self.assertRaisesRegex(frappe.ValidationError, "Only a resolved"):
            close_request(draft.name)

    def test_close_then_reopen_round_trips_a_resolved_submitted_request(self):
        """The acceptance case: close reaches Closed, and reopen returns it to Open with a reason."""
        record = _new_request()
        record.submit()
        record.db_set("status", "Resolved")

        close_request(record.name)
        self.assertEqual(frappe.db.get_value("Maintenance Request", record.name, "status"), "Closed")

        with self.assertRaisesRegex(frappe.ValidationError, "reason is required"):
            reopen_request(record.name, "")

        reopen_request(record.name, "Issue recurred")
        self.assertEqual(frappe.db.get_value("Maintenance Request", record.name, "status"), "Open")
