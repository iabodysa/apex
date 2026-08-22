# Copyright (c) 2026, afmcoltd
"""Trip Start Log controller.

Execution record for a worker-transport trip (the Workers division of Salis,
branded "Masar"). It captures, against a Dispatch Trip, the start/end times, the
expected headcount, and a boarding-event child table (who boarded, where, when,
and how — QR or Manual). Registered workers come from the linked Transport
Request's manifest; unregistered contractors/temp hires are supported on the
child row (``is_unregistered``).

Boundary: this is a purely operational headcount record. It posts **no GL Entry
/ Journal Entry** and creates no accounting documents — consistent with the
Salis no-financial-impact rule. The controller is light: it derives the counts
(``expected_count`` from the request manifest, ``boarded_count`` from the child
rows — both read-only, never hand-set) and validates each boarding row; it never
moves money and owns no cross-document side-effects.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.salis.utils import get_driver_for_user


class TripStartLog(Document):
    def validate(self):
        """Validates boarding, derives counts, and checks driver ownership."""
        self._validate_boarding_rows()
        self._derive_counts()
        self._validate_times()
        self._check_driver_ownership()

    def _check_driver_ownership(self):
        """Prevent one driver from writing another driver's Trip Start Log.

        WHO the caller is comes from ``salis.utils.get_driver_for_user`` — the app's
        single driver resolver — never from a ``driver_user`` lookup on
        ``frappe.session.user``. Since the barcode cutover a driver has no Frappe
        User at all: identity arrives as a hashed bearer token and the session is
        Guest, so a session-User lookup resolved nothing for every real driver and
        this guard passed everything through. The resolver reads the presented
        driver credential first and only falls back to the signed-in
        User -> Employee -> Salis Driver link when the request carries no
        credential, so the portal endpoints and this guard can never disagree about
        who is calling.

        A presented credential cannot yield an unresolved driver: the resolver
        passes ``required=True``, so an invalid, blank, expired or non-Active one
        raises PermissionError inside ``resolve_portal_subject`` instead of
        returning None. The permissive branch below is therefore unreachable from
        any request that presents a driver credential.

        Resolving to no driver means the caller is not a driver, and that is the
        only thing it can mean: a desk user (Fleet Manager, Fleet Supervisor,
        Administrator), a scheduled job, a patch or a ``bench migrate``, none of
        which carry a request or a driver-linked User. All of those stay
        unrestricted — this guard scopes a driver to their own record and is not
        the DocPerm that decides who may touch the DocType. The worker (Masar) and
        supervisor portals also save this log via their own token audiences; those
        present no DRIVER credential, so they too keep passing.
        """
        driver = get_driver_for_user()
        if not driver:
            return
        if self.driver and self.driver != driver:
            frappe.throw(
                _("You can only save Trip Start Logs assigned to your own driver record."),
                frappe.PermissionError,
            )

    def _validate_boarding_rows(self):
        """Each boarding row identifies exactly one worker: a registered Employee
        (``worker``) OR an unregistered contractor/temp (``is_unregistered`` with a
        name or contractor id). This keeps the headcount honest and the
        unregistered path explicit. No worker may board twice — a duplicate row
        would inflate ``boarded_count`` and corrupt the headcount reconciliation."""
        seen_workers = set()
        seen_unregistered = set()
        for row in self.boarding_events:
            if row.is_unregistered:
                if not (row.worker_name or row.contractor_id):
                    frappe.throw(
                        _(
                            "Boarding row #{0}: an unregistered worker needs a name or a contractor/temp id."
                        ).format(row.idx)
                    )
                key = (row.contractor_id or row.worker_name or "").strip().casefold()
                if key:
                    if key in seen_unregistered:
                        frappe.throw(
                            _(
                                "Boarding row #{0}: this worker has already boarded on this trip."
                            ).format(row.idx)
                        )
                    seen_unregistered.add(key)
            elif not row.worker:
                frappe.throw(
                    _(
                        "Boarding row #{0}: select a Worker, or tick 'Unregistered' and give a name/id."
                    ).format(row.idx)
                )
            else:
                if row.worker in seen_workers:
                    frappe.throw(
                        _(
                            "Boarding row #{0}: worker {1} has already boarded on this trip."
                        ).format(row.idx, row.worker)
                    )
                seen_workers.add(row.worker)

    def _derive_counts(self):
        """Derive both counts server-side; neither is hand-set.

        - ``expected_count`` = the linked Transport Request's registered worker
          count (its manifest size).
        - ``boarded_count`` = the number of boarding event rows.
        """
        self.boarded_count = len(self.boarding_events or [])
        expected = 0
        if self.transport_request:
            expected = (
                frappe.db.get_value(
                    "Transport Request", self.transport_request, "worker_count"
                )
                or 0
            )
        self.expected_count = expected

    def _validate_times(self):
        """End cannot precede start when both are set."""
        if self.start_datetime and self.end_datetime:
            if self.end_datetime < self.start_datetime:
                frappe.throw(
                    _("End Datetime cannot be earlier than Start Datetime.")
                )
