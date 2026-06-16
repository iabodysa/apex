# Copyright (c) 2026, AFMCO and contributors
# [#m4uz3c]

"""Global email kill-switch for the Apex app.

A single source of truth for "is the app allowed to send email at all?". Every
explicit ``frappe.sendmail(...)`` call site must guard on :func:`email_enabled`
so the app stays silent unless an administrator has deliberately turned email on
in Habitat Settings.

The toggle (``enable_email_notifications`` on the ``Habitat Settings`` single)
defaults to OFF, so a fresh install never emails anyone until it is enabled.

This gate covers the *imperative* send path only. The declarative paths are
off by default in their own metadata and an admin enables them individually:

* Frappe **Notification** records ship with ``enabled: 0`` in their fixtures.
* **Auto Email Report** records are seeded with ``enabled: 0``.

This is intentionally a tiny, dependency-light helper so it can be imported from
controllers, scheduler tasks, or seeders without pulling in heavier modules.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint


def email_enabled() -> bool:
    """Return ``True`` only if the master email toggle is ON.

    Reads the ``enable_email_notifications`` flag on the ``Habitat Settings``
    single. Defaults to ``False`` (kill-switch closed) — including when the
    Single row does not yet exist on a fresh site — so email never leaves the
    system by accident.
    """
    return bool(cint(frappe.db.get_single_value("Habitat Settings", "enable_email_notifications")))
