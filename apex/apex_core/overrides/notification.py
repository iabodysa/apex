# Copyright (c) 2026, afmcoltd
"""App-layer override of the core Notification channel dispatch.

Registered via ``override_doctype_class`` in ``hooks.py`` (NOT a core
monkey-patch). It changes two behaviours and nothing else:

FIRST, it is where the Habitat Settings email kill-switch reaches the DECLARATIVE
send path. The ``enable_email_notifications`` toggle on Habitat Settings is read
by every explicit ``frappe.sendmail`` call site in this app, and a Notification
record reaches
``frappe.sendmail`` through core rather than through any of them — so with the
switch OFF the eighteen records this app ships with ``enabled: 1`` and
``channel: Email`` would still send. This class is the one place all of them pass
through. The in-app System Notification is deliberately NOT gated: the switch is
named for outgoing email and says so.

SECOND:

Core ``Notification.send_notification_by_channel`` runs the primary channel
(Email/Slack/SMS) inside a single ``try`` and only *afterwards* creates the
in-app System Notification. So on a site with no default outgoing Email
Account, ``send_an_email`` -> ``frappe.sendmail`` raises, the ``except`` logs
"Failed to send Notification", AND the ``send_system_notification`` block that
follows never runs — the bell stays silent even though it is the resilient
fallback the notification opted into.

This override delivers the in-app System Notification FIRST (independent of the
email transport) and, when that in-app path succeeded, a subsequent
email/transport failure never blocks or reverts it — the bell stands regardless.
The failure is still logged: silencing it would leave a broken SMTP/Slack/SMS
transport with no record anywhere, which reads as delivered when nothing left
the building. Recipients, conditions, and the notifications actually produced
are unchanged — only ordering + error resilience differ.
"""

import frappe
from frappe.email.doctype.notification.notification import Notification


class ApexNotification(Notification):
    def send_notification_by_channel(self, doc, context):
        """Sends the in-app notification first; a later channel failure is always
        logged but never reverts or blocks it once the in-app path landed."""
        system_path = self.channel == "System Notification" or self.send_system_notification
        if system_path:
            try:
                self.create_system_notification(doc, context)
            except Exception:
                self.log_error("Failed to send Notification")

        if self.channel == "System Notification":
            return

        if self.channel == "Email" and not frappe.db.get_single_value("Habitat Settings", "enable_email_notifications"):
            return

        try:
            if self.channel == "Email":
                self.send_an_email(doc, context)
            elif self.channel == "Slack":
                self.send_a_slack_msg(doc, context)
            elif self.channel == "SMS":
                self.send_sms(doc, context)
        except Exception:
            self.log_error("Failed to send Notification")
