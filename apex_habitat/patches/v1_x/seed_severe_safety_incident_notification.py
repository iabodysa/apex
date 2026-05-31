"""Seed the "Habitat - Severe Safety Incident" management-escalation Notification
on existing sites.

Guarded and idempotent: delegates to the single source of truth
``seed_operational_notifications`` (also called from setup.after_install for fresh
installs), which skips any Notification that already exists. This patch is the
migrate path that reaches already-installed sites. A no-op on re-run and on sites
that already have the record. Wrapped so a failure (e.g. a missing role on a
partial install) rolls back and logs rather than breaking migrate.
"""

import frappe

from apex_habitat.habitat.notifications_seed import seed_operational_notifications


def execute():
    try:
        seed_operational_notifications()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="seed_severe_safety_incident_notification failed",
            message=frappe.get_traceback(),
        )
