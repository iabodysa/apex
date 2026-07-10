# Copyright (c) 2026, AFMCO and contributors
"""Salis Driver Portal — notifications endpoints (split from the driver_portal god module in P-180). Kernel helpers are imported from the package so the canonical dotted path apex_habitat.salis.api.driver_portal.<fn> is unchanged."""

import frappe

from apex_habitat.salis.api.driver_portal import (
    _resolve_driver,
    _require_enabled,
)


@frappe.whitelist()
def get_my_notifications(limit=20):
	"""The current user's recent native Notification Log rows (read).

	Identity-scoped: filtered to ``for_user = session user`` (never client-supplied),
	so it only ever returns the caller's own notifications. These are the system
	notifications native Frappe writes when a Salis Notification with
	``send_system_notification`` fires at the driver's user — the driver-facing
	channels (blocked-driver clearance, fuel-overdue, vehicle-compliance, trip
	scheduled). Backs the Home screen's notifications strip/bell.

	Each row carries subject, a plain-text body (the email_content stripped of HTML),
	the read flag, and a stringified ``creation`` timestamp (newest first). Read-only,
	no commit; never raises for a driver with no notifications (returns an empty list).
	"""
	_require_enabled()
	_resolve_driver()  # gate: only a linked driver sees the feed
	rows = frappe.get_all(
		"Notification Log",
		filters={"for_user": frappe.session.user},
		fields=["name", "subject", "email_content", "read", "creation", "document_type", "document_name"],
		order_by="creation desc",
		limit=frappe.utils.cint(limit) or 20,
	)
	for r in rows:
		r["read"] = bool(r.get("read"))
		r["creation"] = frappe.utils.cstr(r["creation"]) if r.get("creation") else None
		# strip the notification's HTML so the SPA renders a clean line, not markup
		r["body"] = frappe.utils.strip_html_tags(r.get("email_content") or "").strip() or None
		r.pop("email_content", None)
	return rows



@frappe.whitelist()
def get_push_config():
	"""Web Push opt-in config for the SPA (read).

	Identity-scoped: only a linked driver behind an enabled portal gets here. Returns
	whether background push is configured (the operator enabled it AND a VAPID key pair
	is present) and, when so, the PUBLIC VAPID key the browser subscribes with. The
	private key is never exposed. ``subscribed`` reports whether this user already has
	an enabled device, so the SPA shows the right opt-in/opt-out state.

	When push is unconfigured this is a friendly ``{"enabled": False}`` (never a 403),
	so the SPA simply hides the opt-in — the no-op-until-wired contract end to end."""
	_require_enabled()
	driver = _resolve_driver()
	from apex_habitat.salis.api import web_push

	key = web_push.public_key()
	if not key:
		return {"enabled": False, "subscribed": False}
	return {
		"enabled": True,
		"vapid_public_key": key,
		"subscribed": bool(
			frappe.db.exists(
				"Driver Push Subscription",
				{"driver": driver, "user": frappe.session.user, "enabled": 1},
			)
		),
	}



@frappe.whitelist(methods=["POST"])
def delete_push_subscription(endpoint):
	"""Opt the driver's device out of Web Push (write).

	Identity-scoped: only the caller's own subscription (matched on driver + endpoint)
	is disabled, so one driver can never opt another's device out. Disables rather than
	deletes so the device history is auditable. Idempotent — an unknown endpoint is a
	silent success. Returns ``{"disabled": bool}``."""
	_require_enabled()
	driver = _resolve_driver()
	endpoint = (endpoint or "").strip()
	name = frappe.db.get_value(
		"Driver Push Subscription", {"driver": driver, "endpoint": endpoint}, "name"
	)
	if not name:
		return {"disabled": False}
	frappe.db.set_value("Driver Push Subscription", name, "enabled", 0)
	return {"disabled": True}

