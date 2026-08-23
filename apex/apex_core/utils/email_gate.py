# Copyright (c) 2026, afmcoltd

"""Recipient consent filter for the Apex app.

Every explicit ``frappe.sendmail(...)`` call site asks two questions. The first —
"is the app allowed to send email at all?" — is the ``enable_email_notifications``
flag on the ``Habitat Settings`` single, read directly at each site; it defaults to
OFF, so a fresh install never emails anyone until an administrator turns it on. The
second is :func:`mailable`: "did this person agree to receive?". Asking only the
first mails people who switched their own notifications off.

The toggle covers the *imperative* send path plus the Notification override in
``apex_core/overrides/notification.py``. The two declarative paths do NOT share one
policy, and the difference matters:

* **Auto Email Report** records are seeded disabled — ``enabled: 0`` in
  ``auto_email_report_seed_base.py`` — so an administrator turns each one on.
* Frappe **Notification** records do not follow that rule. 23 of the 36 records this
  app ships carry ``enabled: 1``; 13 ship disabled. What keeps a fresh install quiet
  is the toggle above, not the record metadata.
"""

from __future__ import annotations

import frappe
from frappe.desk.doctype.notification_settings.notification_settings import (
    is_email_notifications_enabled,
)


def mailable(users) -> list[str]:
    """Keep only the addresses that can be emailed, in the order given.

    The Habitat Settings toggle answers whether the APP may send at all; this answers
    whether a PERSON agreed to receive. They are different questions and both must be
    asked: ``frappe.sendmail`` honours neither, and ``frappe.db.get_value("User", u,
    "enabled")`` is the LOGIN flag, so a user who is perfectly able to log in and has
    switched their own email notifications off still passes it.

    Administrator and Guest are dropped: neither is a person who chose anything.

    ``users`` also carries a plain email address with no matching ``User`` row on sites
    where a recipient is configured directly (``Habitat Settings.finance_notification_email``,
    ``safety_report_recipient``) — an external contact who never logs in. Such an address
    has no login to disable and no Notification Settings to opt out with, so
    ``frappe.db.get_value("User", ...)`` returning nothing is read as "not a User", not as
    "blocked", and the address passes through unfiltered — the same default
    ``is_email_notifications_enabled`` already applies to a User with no Notification
    Settings row.
    """
    out = []
    for user in users or []:
        if not user or user in ("Administrator", "Guest"):
            continue
        enabled = frappe.db.get_value("User", user, "enabled")
        if enabled is None:
            out.append(user)
            continue
        if not enabled:
            continue
        if not is_email_notifications_enabled(user):
            continue
        out.append(user)
    return out
