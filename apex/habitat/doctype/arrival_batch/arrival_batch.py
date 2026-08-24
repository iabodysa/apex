# Copyright (c) 2026, afmcoltd
"""Arrival Batch controller.

A pre-arrival manifest: the workers a labour supplier expects to deliver to a
building on a date. It is both a front-desk intake surface (suppliers submit it
via the public Arrival Manifest web form) and the backend record the Arrivals
Desk reconciles real arrivals against; get_arrival_summary measures manifest
completion from expected_count. Title and expected_count are derived in validate
and each row's "Arrived As" is set during reconciliation, so all three are
read-only by design.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.portal_live import notify_building

_MAX_EXPECTED_WORKERS = 500


class ArrivalBatch(Document):
    def validate(self) -> None:
        """Blocks a honeypot-filled or empty or over-500 worker manifest, and sets
        expected_count and the batch title.

        The honeypot is read HERE, not only in submit_arrival_manifest: the live public
        form saves through Frappe's own ``web_form.accept``, which copies every web form
        field onto the document (frappe/website/doctype/web_form/web_form.py:632-647) and
        never touches the hardened endpoint beside it."""
        if self.get("website_field"):
            frappe.throw(_("Invalid submission."), frappe.PermissionError)

        self._clear_guest_reconciliation_rows()
        self.expected_count = len(self.expected_workers or [])
        if self.expected_count > _MAX_EXPECTED_WORKERS:
            frappe.throw(
                _("A manifest can list at most {0} expected workers.").format(_MAX_EXPECTED_WORKERS)
            )
        self.title = f"{self.building} - {frappe.utils.formatdate(self.expected_date)}"

    def _clear_guest_reconciliation_rows(self):
        """Empties each expected worker's "Arrived As" link on a new Guest submission.

        ``temporary_worker`` is read_only because reconciliation sets it at the desk,
        never the supplier who files the manifest. A Guest reaches this document through
        Frappe's own Web Form ``accept``, which builds it from the POST body and calls
        ``insert()`` (frappe/website/doctype/web_form/web_form.py:598-663), and
        ``validate_higher_perm_levels`` skips the child-row reset while the parent is new
        (frappe/model/document.py:783-806) — so nothing upstream blanks a value a POST
        put there. Clearing it here keeps a supplier from naming which Temporary Worker
        a row already is.
        """
        if not (self.is_new() and frappe.session.user == "Guest"):
            return
        for row in self.expected_workers or []:
            row.temporary_worker = None

    def on_update(self):
        """Rings the building's watchers so an open Arrivals Desk shows a new or amended
        manifest without a reload.

        A supplier files this manifest through the public web form, so the change arrives
        with nobody at a desk having asked for it — the receptionist reconciling arrivals
        against it is the one who must see it appear."""
        notify_building(self.building)

    @property
    def pending_arrival_count(self) -> int:
        """Returns how many expected workers still lack a submitted Housing Assignment for the date."""
        housed = frappe.db.count(
            "Housing Assignment",
            {
                "building": self.building,
                "check_in_date": self.expected_date,
                "docstatus": 1,
            },
        )
        return max(int(self.expected_count or 0) - housed, 0)
