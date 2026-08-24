# Copyright (c) 2026, afmcoltd

import frappe
from frappe.email.doctype.notification.notification import Notification


class ApexNotification(Notification):
    def send_notification_by_channel(self, doc, context):
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
