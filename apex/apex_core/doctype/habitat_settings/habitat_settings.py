# Copyright (c) 2026, afmcoltd
"""Habitat Settings controller.

Single DocType holding global integration toggles. All defaults are
conservative: no financial posting unless explicitly enabled.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class HabitatSettings(Document):
    pass


def before_save(doc, method=None):
    """Stamp the editor's top role on the document.

    Who may write is the DocPerm's answer — System Manager alone holds write here — and
    repeating it in Python refuses the installer too, because the setup wizard writes
    these settings through ``ignore_permissions`` and a hand-written role check does not
    honour that flag.
    """
    roles = frappe.get_roles(frappe.session.user)
    doc.last_modified_by_role = roles[0] if roles else ""


def get_default_company() -> str | None:
    """Resolve the company applied to Habitat transactions when not set explicitly.

    Thin wrapper over the shared resolver (explicit Habitat Settings ``company``
    -> user company default -> global company default), so Habitat resolves a
    company the same way Salis does. Returns ``None`` when none is configured.
    """
    from apex.apex_core.utils.company import resolve_company

    return resolve_company("Habitat")
