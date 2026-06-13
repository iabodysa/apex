"""Employee Deduction Acknowledgment (Mahdar Iqrar) controller.

An employee CONSENT record for a single salary deduction (damage / rent / fuel /
custody). Under KSA Labor Law this kind of wage deduction needs the worker's
consent; the Salary Deduction Policy requires a submitted, approved acknowledgment
for the source reference before the deduction is posted.

Native-first: the worker identity uses the same ``party_type`` / ``party`` Dynamic
Link as the other housed-worker doctypes (see ``apex_core.utils.party_link``); the
eventual deduction is an HRMS ``Additional Salary`` (linked via
``linked_additional_salary``). This DocType only captures and gates consent.

Skeleton only. ``validate`` / ``on_submit`` enforce consent integrity on THIS record
and keep the Employee mirror in step; they do NOT reach into or import any
operational controller (custody_damage_assessment, accommodation_checkout, fuel,
salis). Posting the Additional Salary from the acknowledgment is a later increment.
"""

from __future__ import annotations

from frappe.model.document import Document
from frappe.utils import now_datetime

from apex_habitat.apex_core.utils.party_link import sync_party_employee


class EmployeeDeductionAcknowledgment(Document):
    def validate(self):
        # Keep party_type / party and the read-only Employee mirror in step, exactly
        # like the other housed-worker doctypes. Self-contained: touches only this doc.
        sync_party_employee(self, require_party=True)
        if self.approval_status == "Approved":
            if not self.approved_on:
                self.approved_on = now_datetime()
        else:
            # Clear the approval stamp if it is moved off Approved.
            self.approved_on = None
            self.approved_by = None

    def on_submit(self):
        # A submitted acknowledgment is the consent of record: it must actually carry
        # consent. Kept self-contained (no cross-doctype wiring in the skeleton).
        from frappe import _, throw

        if not self.consent_given:
            throw(_("Consent Given must be checked before submitting the acknowledgment."))
