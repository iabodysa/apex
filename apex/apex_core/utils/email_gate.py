# Copyright (c) 2026, AFMCO and contributors

"""Global email kill-switch for the Apex app.

Two questions, both of which every explicit ``frappe.sendmail(...)`` call site must
ask. :func:`email_enabled` answers "is the app allowed to send email at all?", so the
app stays silent unless an administrator turned email on in Habitat Settings.
:func:`mailable` answers "did this person agree to receive?" and filters the recipient
list. Asking only the first mails people who switched their own notifications off.

The toggle (``enable_email_notifications`` on the ``Habitat Settings`` single)
defaults to OFF, so a fresh install never emails anyone until it is enabled.

This gate covers the *imperative* send path only. The two declarative paths do NOT
share one policy, and the difference matters:

* **Auto Email Report** records are seeded disabled — ``enabled: 0`` in
  ``auto_email_report_seed_base.py`` — so an administrator turns each one on.
* Frappe **Notification** records do not follow that rule. 23 of the 36 records this
  app ships carry ``enabled: 1``; 13 ship disabled. What keeps a fresh install quiet
  is the toggle above, not the record metadata.

The shipped value is a FIRST-INSTALL default and nothing more.
``frappe/modules/import_file.py:33`` lists ``"Notification": ["enabled"]`` in
``ignore_values``, so once the record exists on a site an app update never writes that
field again — whatever the administrator chose is permanent, and shipping a different
default in a later version reaches new sites only.

This is intentionally a tiny, dependency-light helper so it can be imported from
controllers, scheduler tasks, or seeders without pulling in heavier modules.
"""

from __future__ import annotations

import frappe
from frappe.desk.doctype.notification_settings.notification_settings import (
    is_email_notifications_enabled,
)
from frappe.utils import cint


def email_enabled() -> bool:
    """Return ``True`` only if the master email toggle is ON.

    Reads the ``enable_email_notifications`` flag on the ``Habitat Settings``
    single. Defaults to ``False`` (kill-switch closed) — including when the
    Single row does not yet exist on a fresh site — so email never leaves the
    system by accident.
    """
    return bool(cint(frappe.db.get_single_value("Habitat Settings", "enable_email_notifications")))


def mailable(users) -> list[str]:
    """Keep only the users who can be emailed, in the order given.

    ``email_enabled`` answers whether the APP may send at all; this answers whether
    a PERSON agreed to receive. They are different questions and both must be asked:
    ``frappe.sendmail`` honours neither, and ``frappe.db.get_value("User", u,
    "enabled")`` is the LOGIN flag, so a user who is perfectly able to log in and has
    switched their own email notifications off still passes it.

    The per-user answer is frappe's own — ``is_email_notifications_enabled``
    (``frappe/desk/doctype/notification_settings/notification_settings.py:47``), which
    reads ``Notification Settings.enable_email_notifications`` and defaults to allowed
    when a user has no settings row yet, so an untouched account is not silenced.

    Administrator and Guest are dropped: neither is a person who chose anything.
    """
    out = []
    for user in users or []:
        if not user or user in ("Administrator", "Guest"):
            continue
        if not frappe.db.get_value("User", user, "enabled"):
            continue
        if not is_email_notifications_enabled(user):
            continue
        out.append(user)
    return out
