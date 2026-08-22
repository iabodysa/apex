# Copyright (c) 2026, afmcoltd
"""Salis Settings controller."""

from __future__ import annotations

import base64
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from apex.apex_core.setup.employee_advance_recovery import MAX_RECOVERY_PERCENT

_CSS_COLOR_RE = re.compile(
    r"""^(?:
		\#[0-9A-Fa-f]{3,8}                      # #rgb / #rgba / #rrggbb / #rrggbbaa
		| (?:rgb|rgba|hsl|hsla)\(               # functional notation …
			[0-9.,%\s/deg]+ \)                  # … digits, %, commas, slash, deg, ws only
		| [A-Za-z]+                             # a CSS colour keyword (red, transparent, …)
	)$""",
    re.VERBOSE,
)

_BRAND_LOGO_RE = re.compile(r"^/files/[^\"'<>\s]+$")


class SalisSettings(Document):
    def validate(self):
        """Bounds the advance recovery percent and checks its salary component and the VAPID key."""
        if self.employee_advance_recovery_max_percent is not None and not (
            0 < self.employee_advance_recovery_max_percent <= MAX_RECOVERY_PERCENT
        ):
            frappe.throw(
                _(
                    "Maximum Recovery Percent must be greater than 0 and no more than {0}."
                ).format(int(MAX_RECOVERY_PERCENT))
            )
        if self.enable_employee_advance_recovery:
            if not self.employee_advance_recovery_component:
                frappe.throw(_("Recovery Salary Component is required to enable recovery."))
            component_type = frappe.db.get_value(
                "Salary Component", self.employee_advance_recovery_component, "type"
            )
            if component_type != "Deduction":
                frappe.throw(_("Recovery Salary Component must be a Deduction."))
        self._validate_web_push_public_key()
        self._validate_portal_appearance()

    def on_update(self):
        """Applies the approvals switch to the Salis workflows."""
        apply_approval_switch()

    def _validate_portal_appearance(self):
        """Refuse an accent colour or brand logo that is unsafe to render.

        Both values are written straight into the portal shell — the accent into a CSS
        custom property, the logo into an ``img`` src — and neither the Color nor the
        Attach Image fieldtype validates its own content. This guard is the only thing
        between a typed value and the page, so a non-CSS colour or an off-site,
        markup-bearing or private-file path is refused at save rather than at render.
        """
        accent = (self.accent_color or "").strip()
        if accent and not _CSS_COLOR_RE.match(accent):
            frappe.throw(_("Accent Color must be a valid CSS colour."))

        logo = (self.brand_logo or "").strip()
        if logo and not _BRAND_LOGO_RE.match(logo):
            frappe.throw(_("Brand Logo must be an uploaded file (a /files/ path)."))

    def _validate_web_push_public_key(self):
        """Refuse a VAPID public key the browser will reject at subscribe time.

        ``PushManager.subscribe`` needs the uncompressed P-256 point: 65 bytes whose
        first byte is 0x04. A truncated or re-encoded key decodes to some other length
        and the browser answers "Invalid raw ECDSA P-256 public key" — to the driver
        turning notifications on, never to the person who pasted the key. Checked here
        so the refusal reaches whoever can fix it.
        """
        if not self.enable_web_push:
            return
        raw = (self.web_push_vapid_public_key or "").strip()
        if not raw:
            frappe.throw(_("A Web Push VAPID public key is required to enable web push."))
        padded = raw.replace("-", "+").replace("_", "/")
        padded += "=" * ((4 - len(padded) % 4) % 4)
        try:
            point = base64.b64decode(padded)
        except (ValueError, TypeError):
            frappe.throw(_("The Web Push VAPID public key is not valid base64url."))
        if len(point) != 65 or point[0] != 4:
            frappe.throw(
                _(
                    "The Web Push VAPID public key must decode to 65 bytes starting with 0x04; "
                    "this one decodes to {0}. Paste the uncompressed public key, not a "
                    "truncated or DER-encoded one."
                ).format(len(point))
            )


def apply_approval_switch():
    """Activate or deactivate every Salis workflow to match ``enable_approvals``.

    ``Workflow.is_active`` is the framework's own switch and the only one there is —
    ``get_workflow_name`` reads it and returns nothing when it is 0, so a document then
    saves with no state gate. A setting that does not reach this field decides nothing.

    The workflows are found through their document type's module rather than a list, so a
    new Salis workflow is covered on the day it ships.

    CONTRACT: an administrator's own change to ``is_active`` on the Workflow list does not
    survive a migrate, because the workflows ship in ``apex/fixtures/`` and a fixture is
    reimported with ``force=True``. This function is what puts the setting's answer back;
    without it the fixture's ``is_active`` of 1 is the only answer any site ever has.
    """
    if not frappe.db.exists("DocType", "Workflow"):
        return
    enabled = cint(frappe.db.get_single_value("Salis Settings", "enable_approvals"))
    salis_doctypes = frappe.get_all("DocType", filters={"module": "Salis"}, pluck="name")
    if not salis_doctypes:
        return
    for name in frappe.get_all(
        "Workflow", filters={"document_type": ["in", salis_doctypes]}, pluck="name"
    ):
        if cint(frappe.db.get_value("Workflow", name, "is_active")) != enabled:
            frappe.db.set_value("Workflow", name, "is_active", enabled)


def get_salis_int(field: str, default: int) -> int:
    """Read an Int from the Salis Settings single, falling back to ``default``
    when the stored value is blank or zero (the new-Single-Int-stores-0 trap)."""
    try:
        value = frappe.db.get_single_value("Salis Settings", field)
    except Exception:
        return default
    if not value:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_salis_float(field: str, default: float) -> float:
    """Read a Float/Currency from the Salis Settings single, falling back to
    ``default`` when the stored value is blank or zero (the zero-trap)."""
    try:
        value = frappe.db.get_single_value("Salis Settings", field)
    except Exception:
        return default
    if not value:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


BOARDING_FLOW_DEFAULTS = {
    "boarding_notify_max_count": 3,
    "boarding_notify_window_seconds": 60,
    "boarding_grace_minutes": 3,
    "boarding_auto_confirm_minutes": 15,
    "worker_wait_request_max": 3,
    "worker_wait_request_seconds": 60,
    "boarding_active_poll_seconds": 10,
}


def get_boarding_setting(key: str) -> int:
    """Return a boarding-flow Int setting, falling back to its built-in default
    when the stored value is blank or zero (the new-Single-Int-stores-0 trap)."""
    if key not in BOARDING_FLOW_DEFAULTS:
        raise KeyError(key)
    value = frappe.db.get_single_value("Salis Settings", key)
    return int(value) if value else BOARDING_FLOW_DEFAULTS[key]


def get_boarding_settings() -> dict:
    """All six boarding-flow tunables as a single dict (value-or-default applied),
    for the SPAs to fetch the limits/window/poll cadence in one read."""
    return {key: get_boarding_setting(key) for key in BOARDING_FLOW_DEFAULTS}


def get_default_company():
    """Resolve the company applied to Salis transactions when not set explicitly.

    Thin wrapper over the shared resolver (explicit Salis Settings default ->
    user company default -> global company default). Returns ``None`` when no
    company is configured (no posting is performed regardless).
    """
    from apex.apex_core.utils.company import resolve_company

    return resolve_company("Salis")


def get_default_cost_center():
    """Resolve the default cost center for fleet cost references.

    Falls back from the explicit Salis Settings default to the resolved
    company's own default cost center. Returns ``None`` when none is configured.
    """
    cost_center = frappe.db.get_single_value("Salis Settings", "default_cost_center")
    if not cost_center:
        company = get_default_company()
        if company and frappe.db.exists("Company", company):
            cost_center = frappe.get_cached_value("Company", company, "cost_center")
    return cost_center or None
