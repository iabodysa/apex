# Copyright (c) 2026, afmcoltd
import frappe


def system_insert(doc, ignore_if_duplicate=False, ignore_mandatory=False):
    """Insert a document the system itself owns, past the acting user's permissions.

    The bypass lives behind this NAME so a reader of the call site sees what is being
    granted without a comment beside it — a comment drifts from the line it sits on and
    is invisible from the caller. Every write routed here is one the application decides
    to make: a seeder, an installer, a scheduled job, a controller acting for the system
    rather than for whoever happened to trigger it. A write that should be refused when
    the user lacks permission must NOT come through here.
    """
    return doc.insert(
        ignore_permissions=True,
        ignore_if_duplicate=ignore_if_duplicate,
        ignore_mandatory=ignore_mandatory,
    )


def system_save(doc):
    """Save a document the system itself owns, past the acting user's permissions.

    Same contract as :func:`system_insert`. Use it where the application, not the user,
    is the author of the change.
    """
    return doc.save(ignore_permissions=True)


def system_delete(doctype, name, force=False, ignore_missing=True):
    """Delete a document the system itself owns, past the acting user's permissions.

    ``ignore_missing`` defaults True because the callers are cleanups and re-runnable
    installers, for which an already-absent record is success, not an error.
    """
    return frappe.delete_doc(
        doctype,
        name,
        force=force,
        ignore_permissions=True,
        ignore_missing=ignore_missing,
    )
