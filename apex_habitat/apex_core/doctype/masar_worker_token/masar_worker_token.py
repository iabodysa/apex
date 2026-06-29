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

from apex_habitat.apex_core.utils.party_link import sync_party_employee

TOKEN_BYTES = 24  # [#9dvf8n]

# [#tokttl] How long a freshly minted/rotated personal link stays valid. A leaked
# /masar link is no longer valid forever (T-629); a worker re-opens (or a supervisor
# re-shares via Show Link) well within this window, and Show Link / Regenerate both
# extend it. 180 days is generous enough that a normally-active worker's link never
# silently expires under them, while bounding the lifetime of a leaked link.
TOKEN_TTL_DAYS = 180


def _token_expiry():
    """The expiry stamp for a freshly issued/extended link: now + the TTL window."""
    return frappe.utils.add_to_date(frappe.utils.now_datetime(), days=TOKEN_TTL_DAYS)


def _new_token() -> str:
    """A fresh url-safe random token, guaranteed unique across the doctype."""
    for _attempt in range(8):
        candidate = frappe.generate_hash(length=TOKEN_BYTES * 2)
        if not frappe.db.exists("Masar Worker Token", {"token": candidate}):
            return candidate
    # [#s3grro]
    frappe.throw(_("Could not generate a unique worker token. Please try again."))


class MasarWorkerToken(Document):
    # [#pewmoc]
    def before_validate(self):
        sync_party_employee(self, require_party=True)
        # [#t325tw] Masar is Employee-only (T-325): a Temporary Worker has no
        # Employee-keyed data to surface, so a temp token would mint a dead link.
        # Refuse it at source; the daily linking engine re-points the party to a
        # real Employee (raw SQL, so it is unaffected by this guard).
        if self.party_type == "Temporary Worker":
            frappe.throw(
                _(
                    "A Masar worker link can only be issued to an Employee. "
                    "This worker is linked once their Iqama is issued and a permanent Employee record exists."
                )
            )

    def before_insert(self):
        # autoname is field:party, which set_new_name resolves BEFORE before_validate
        # runs — so a token created with only the Employee link (get_or_create_for_employee)
        # would otherwise hit naming with an empty party ("Worker is required"). Mirror
        # employee -> party here so naming has it; before_validate still runs the full
        # require_party + Temporary-Worker guard.
        sync_party_employee(self)
        # [#img31u]
        self.token = _new_token()
        # [#tokttl] Stamp the link's expiry on mint so a leaked link cannot live forever.
        self.expires_on = _token_expiry()
        self.last_generated_on = frappe.utils.now_datetime()
        self.last_generated_by = frappe.session.user

    def regenerate(self):
        """Rotate the token (invalidates any previously shared link/QR)."""
        self.token = _new_token()
        # [#tokttl] A rotation issues a fresh link, so it also resets the expiry window.
        self.expires_on = _token_expiry()
        self.last_generated_on = frappe.utils.now_datetime()
        self.last_generated_by = frappe.session.user
        self.save()
        return self.token

    def extend_expiry(self):
        """Push the expiry out by a fresh TTL window WITHOUT rotating the token.

        Show Link re-shares the SAME distributed link, so it must keep that link
        alive (a worker who is still active should never lose their link just because
        the window lapsed). Token + QR are unchanged; only ``expires_on`` advances."""
        self.expires_on = _token_expiry()
        self.last_generated_on = frappe.utils.now_datetime()
        self.last_generated_by = frappe.session.user
        self.save()
        return self.expires_on


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


@frappe.whitelist(methods=["POST"])
def issue_worker_link(employee: str, regenerate: int = 0) -> dict:
    """Desk action: issue (or rotate) a worker's personal Masar link + QR.

    Permission-gated on write access to Masar Worker Token. Returns the link, the
    token, an SVG data-URI QR image (or None if QR rendering is unavailable), and
    the worker's phone (Employee.cell_number) so the caller can offer a WhatsApp
    share. No financial impact."""
    frappe.has_permission("Masar Worker Token", "write", throw=True)
    doc = get_or_create_for_employee(employee)
    if frappe.utils.cint(regenerate) and doc.token:
        doc.regenerate()
    elif not doc.token:
        # [#gl1eyq]
        doc.regenerate()
    else:
        # [#tokttl] Re-sharing the SAME link keeps it alive: push the expiry out so a
        # still-active worker never loses their distributed link to a lapsed window.
        doc.extend_expiry()

    link = _worker_link(doc.token)
    return {
        "employee": doc.employee,
        "employee_name": doc.employee_name,
        "enabled": bool(doc.enabled),
        "token": doc.token,
        "link": link,
        "qr": masar_qr_data_uri(link),
        "expires_on": frappe.utils.cstr(doc.expires_on) if doc.expires_on else None,
        # [#p7spkl]
        "phone": frappe.db.get_value("Employee", doc.employee, "cell_number"),
    }


@frappe.whitelist(methods=["POST"])
def batch_issue_worker_links(employees_json) -> list:
    """Issue (or fetch) the Masar link + QR for several Employees in ONE call — the
    Arrivals Desk group-QR action. Same per-worker behaviour as issue_worker_link
    (mints a token when missing), permission-checked once. Returns one row per
    Employee: ``{employee, employee_name, link, qr, phone}``."""
    frappe.has_permission("Masar Worker Token", "write", throw=True)
    employees = frappe.parse_json(employees_json) or []
    out = []
    for emp in employees:
        doc = get_or_create_for_employee(emp)
        if not doc.token:
            doc.regenerate()
        else:
            # [#tokttl] Batch re-share keeps each existing link alive (fresh expiry).
            doc.extend_expiry()
        link = _worker_link(doc.token)
        out.append(
            {
                "employee": doc.employee,
                "employee_name": doc.employee_name,
                "link": link,
                "qr": masar_qr_data_uri(link),
            }
        )
    # Resolve every cell_number in ONE query, then fill — not one get_value per row.
    emp_ids = [r["employee"] for r in out if r.get("employee")]
    phones = dict(
        frappe.get_all(
            "Employee",
            filters={"name": ["in", emp_ids]},
            fields=["name", "cell_number"],
            as_list=True,
        )
    ) if emp_ids else {}
    for r in out:
        r["phone"] = phones.get(r["employee"])
    return out


def masar_qr_data_uri(text: str):
    """Render ``text`` as a base64 SVG data-URI QR, or None if unavailable.

    Uses ``pyqrcode`` (bundled with Frappe — ``frappe.twofactor`` relies on it;
    the ``qrcode`` package is NOT installed on the bench). pyqrcode emits a crisp,
    tiny vector SVG that scales cleanly on screen and in print. Kept defensive so a
    missing optional dependency degrades to a plain link rather than erroring the
    desk action."""
    try:
        import io
        from base64 import b64encode

        import pyqrcode  # [#9xz9bo]

        q = pyqrcode.create(text)
        buf = io.BytesIO()
        q.svg(buf, scale=4)
        return "data:image/svg+xml;base64," + b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None
