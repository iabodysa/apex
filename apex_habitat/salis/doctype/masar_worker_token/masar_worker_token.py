"""Masar Worker Token — personal access link for the worker self-service app.

Each row binds ONE Employee to an unguessable random ``token``. The worker opens
their personal URL ``/masar?w=<token>`` (or scans the matching QR); the Masar
worker endpoints resolve that token server-side back to this single Employee and
scope every query to them. The client never supplies an Employee id, so one
token can only ever surface its own worker's data.

Why a dedicated link DocType (not Custom Fields on Employee): adding fields to
the standard HRMS Employee needs a Custom Field fixture + hooks wiring and
clutters the HR form. A small purpose-built record is auto-discovered by Frappe,
owns its own desk action (generate / regenerate + QR), keeps the access token
off the Employee master, and makes token-scoping a single indexed lookup.

No financial impact: this is identity/issuance metadata only.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

TOKEN_BYTES = 24  # ~32 url-safe chars of entropy — unguessable.


def _new_token() -> str:
    """A fresh url-safe random token, guaranteed unique across the doctype."""
    for _attempt in range(8):
        candidate = frappe.generate_hash(length=TOKEN_BYTES * 2)
        if not frappe.db.exists("Masar Worker Token", {"token": candidate}):
            return candidate
    # Astronomically unlikely; fail loudly rather than risk a collision.
    frappe.throw(_("Could not generate a unique worker token. Please try again."))


class MasarWorkerToken(Document):
    def before_insert(self):
        # Always mint server-side; never accept a client-supplied token value.
        self.token = _new_token()
        self.last_generated_on = frappe.utils.now_datetime()
        self.last_generated_by = frappe.session.user

    def regenerate(self):
        """Rotate the token (invalidates any previously shared link/QR)."""
        self.token = _new_token()
        self.last_generated_on = frappe.utils.now_datetime()
        self.last_generated_by = frappe.session.user
        self.save()
        return self.token


def get_or_create_for_employee(employee: str) -> "MasarWorkerToken":
    """Return the worker's token row, creating one on first use."""
    if not frappe.db.exists("Employee", employee):
        frappe.throw(_("Employee {0} does not exist.").format(employee))
    name = frappe.db.get_value("Masar Worker Token", {"employee": employee}, "name")
    if name:
        return frappe.get_doc("Masar Worker Token", name)
    doc = frappe.get_doc({"doctype": "Masar Worker Token", "employee": employee})
    doc.insert()
    return doc


def _worker_link(token: str) -> str:
    """The shareable personal Masar URL for a token."""
    return f"{frappe.utils.get_url()}/masar?w={token}"


@frappe.whitelist()
def issue_worker_link(employee: str, regenerate: int = 0) -> dict:
    """Desk action: issue (or rotate) a worker's personal Masar link + QR.

    Permission-gated on write access to Masar Worker Token. Returns the link, the
    token, and a data-URI QR image when the ``qrcode`` package is available
    (Frappe ships it); otherwise ``qr`` is None and the caller renders the link
    on its own. No financial impact."""
    frappe.has_permission("Masar Worker Token", "write", throw=True)
    doc = get_or_create_for_employee(employee)
    if frappe.utils.cint(regenerate) and doc.token:
        doc.regenerate()
    elif not doc.token:
        # A row that somehow has no token (e.g. legacy import) — mint one.
        doc.regenerate()

    link = _worker_link(doc.token)
    return {
        "employee": doc.employee,
        "employee_name": doc.employee_name,
        "enabled": bool(doc.enabled),
        "token": doc.token,
        "link": link,
        "qr": _qr_data_uri(link),
    }


def _qr_data_uri(text: str):
    """Render ``text`` as a base64 PNG data-URI QR, or None if unavailable.

    Uses the ``qrcode`` package bundled with Frappe. Kept defensive so a missing
    optional dependency degrades to a plain link rather than erroring the desk
    action."""
    try:
        import io
        from base64 import b64encode

        import qrcode  # bundled with frappe

        img = qrcode.make(text)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None
