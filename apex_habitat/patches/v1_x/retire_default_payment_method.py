# Copyright (c) 2026, AFMCO and contributors
"""Retire the inert ``default_payment_method`` Select in favour of the Payment
Routing Settings router.

``default_payment_method`` was only ever read by the Accommodation Lease
``Generate Payment`` button to pick which payment document to build. That choice is
now driven by ``Payment Routing Settings.target_payment_doctype``, so the Select
was removed from Apex Settings (and was never moved there from Habitat Settings).

On a site that set a value, it lingers as an orphan row in ``tabSingles`` under
either ``Apex Settings`` (if a prior build had moved it) or ``Habitat Settings``
(its original home). This patch:

  * reads any old value from those orphan rows (query builder, NOT
    ``get_single_value`` — the field is gone from both metas);
  * seeds it into ``Payment Routing Settings.target_payment_doctype`` ONLY when the
    router is still unconfigured AND the value names an installed DocType (e.g. the
    optional ``Expense Request Afmco`` may be absent), so the router never points at
    a missing target and an explicit router config is never clobbered;
  * deletes the orphan rows from both Singles, so a second run is a pure no-op.

ONE-TIME, idempotent, install-safe (no-op on fresh installs). PRUNE (remove module
+ the patches.txt line) once every deployed site has run it.
"""

import frappe

# [#n1agup] The old field name + the Singles that could carry its orphan value, in
# precedence order (a moved Apex Settings orphan wins over the Habitat original).
_FIELD = "default_payment_method"
_SOURCE_SINGLES = ("Apex Settings", "Habitat Settings")


def execute():
    try:
        singles = frappe.qb.Table("tabSingles")

        old_value = None
        for single in _SOURCE_SINGLES:
            rows = (
                frappe.qb.from_(singles)
                .select(singles.value)
                .where((singles.doctype == single) & (singles.field == _FIELD))
                .run()
            )
            if rows and rows[0][0] not in (None, ""):
                old_value = rows[0][0]
                break

        # Seed the router only if it is unconfigured and the value is a real DocType.
        if old_value and frappe.db.exists("DocType", "Payment Routing Settings"):
            router = frappe.get_single("Payment Routing Settings")
            if not router.target_payment_doctype and frappe.db.exists("DocType", old_value):
                router.target_payment_doctype = old_value
                router.save(ignore_permissions=True)  # audit-ok

        # Delete the orphan rows from every source Single, so a re-run is a no-op.
        frappe.qb.from_(singles).delete().where(
            (singles.doctype.isin(list(_SOURCE_SINGLES))) & (singles.field == _FIELD)
        ).run()
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="retire_default_payment_method failed",
            message=frappe.get_traceback(),
        )
