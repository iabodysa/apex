# Copyright (c) 2026, AFMCO and contributors
"""App-layer override of the core Notification channel dispatch.

Registered via ``override_doctype_class`` in ``hooks.py`` (NOT a core
monkey-patch). It changes ONE behaviour and nothing else:

Core ``Notification.send_notification_by_channel`` runs the primary channel
(Email/Slack/SMS) inside a single ``try`` and only *afterwards* creates the
in-app System Notification. So on a site with no default outgoing Email
Account, ``send_an_email`` -> ``frappe.sendmail`` raises, the ``except`` logs
"Failed to send Notification", AND the ``send_system_notification`` block that
follows never runs — the bell stays silent even though it is the resilient
fallback the notification opted into.

This override delivers the in-app System Notification FIRST (independent of the
email transport) and, when that in-app path succeeded, swallows a subsequent
email/transport failure instead of logging it as a hard error. A notification
with no System Notification fallback keeps the original error-logging behaviour.
Recipients, conditions, and the notifications actually produced are unchanged —
only ordering + error resilience differ.
"""

from frappe.email.doctype.notification.notification import Notification


class ApexNotification(Notification):
    def send_notification_by_channel(self, doc, context):
        # Deliver the in-app System Notification first so the bell always works,
        # independent of Email/Slack/SMS transport availability.
        system_path = self.channel == "System Notification" or self.send_system_notification
        system_sent = False
        if system_path:
            try:
                self.create_system_notification(doc, context)
                system_sent = True
            except Exception:
                self.log_error("Failed to send Notification")

        # The System Notification channel has no separate transport step.
        if self.channel == "System Notification":
            return

        try:
            if self.channel == "Email":
                self.send_an_email(doc, context)
            elif self.channel == "Slack":
                self.send_a_slack_msg(doc, context)
            elif self.channel == "SMS":
                self.send_sms(doc, context)
        except Exception:
            # A missing outgoing Email Account (or any transport failure) must
            # NOT surface as a hard error when the in-app System Notification
            # already delivered — that bell is the resilient fallback path.
            if system_sent:
                return
            self.log_error("Failed to send Notification")
