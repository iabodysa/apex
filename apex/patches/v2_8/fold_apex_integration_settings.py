# Copyright (c) 2026, afmcoltd
"""Fold the Apex Integration Settings Single into Salis Settings and remove it.

One Settings Single per module is the framework's own shape. The frontend-integration
flags and the messaging-gateway config sat in a Single of their own; they now live in
Salis Settings' "Integration" tab, whose own field description names
``salis-fleet.com`` as the worked frontend and whose gateway config is what
``apex.salis.api.messaging_gateway`` reads. ``integration_help`` and
``messaging_gateway_help`` are NOT carried: both are read-only Text Editor fields
whose stored value always equals their own JSON default, so the destination JSON
repeats that default and nothing is lost by skipping the copy.

Values are carried from ``tabSingles`` directly, before anything is deleted, because
the source DocType is about to stop existing and a ``Check`` the operator set to 0
must survive a truthiness test that would drop it and let the destination default
turn the switch back on.

``messaging_gateway_api_key`` is a Password field and is carried separately: its real
value never reaches ``tabSingles``. ``BaseDocument._save_passwords``
(frappe/model/base_document.py:1127) writes the plaintext into ``__Auth`` and leaves
only a dummy asterisk string in the ordinary field, so a ``tabSingles`` copy would
carry a placeholder, not the secret. The Fernet cipher (frappe/utils/password.py:182)
encrypts with the site-wide ``encryption_key`` alone — ``doctype``/``name`` passed to
``decrypt`` are used only in its error message — so the encrypted blob is portable
across doctype/name with no re-encryption needed to move it.

The cleanup here is NOT a table drop: a Single has no ``tab<Name>`` table, so its
values live as ``tabSingles`` rows and its secret as an ``__Auth`` row.
``frappe.delete_doc("DocType", ...)`` leaves both standing — its Singles branch is
reached only when ``doctype != "DocType"`` (frappe/model/delete_doc.py:207), and its
``delete_all_passwords_for`` call clears only ``("DocType", SOURCE)``
(frappe/model/delete_doc.py:65), never the Single instance keyed by
``(SOURCE, SOURCE)``. Those orphan rows are the half-removal this patch avoids.

``frappe/model/sync.py:172 remove_orphan_doctypes`` deletes the orphan DocType
record on its own during migrate, but leaves the value rows behind. This patch runs
in ``post_model_sync``, before that, so it still sees the source and still wins.
"""

import frappe
from frappe.utils.password import (
    delete_all_passwords_for,
    get_decrypted_password,
    set_encrypted_password,
)


SOURCE = "Apex Integration Settings"
TARGET = "Salis Settings"
FIELDS = (
    "integration_enabled",
    "frontend_base_url",
    "api_contract_version",
    "allowed_origins",
    "messaging_gateway_enabled",
    "messaging_gateway_channel",
    "messaging_gateway_url",
    "messaging_gateway_sender_id",
)
PASSWORD_FIELD = "messaging_gateway_api_key"


def execute():
    """Carry the eight plain values and the one secret, then delete the DocType and
    every row it leaves behind.

    The steps are guarded SEPARATELY on purpose. Deleting the DocType leaves both its
    ``tabSingles`` rows and its ``__Auth`` row standing, so a single early return on the
    DocType record would skip both cleanups on exactly the site where the first step
    already ran.
    """
    _carry_values()
    _carry_password()

    if frappe.db.exists("DocType", SOURCE):
        frappe.delete_doc("DocType", SOURCE, force=True)

    _clear_orphan_singles()


def _carry_values():
    """Copy each stored source value onto a destination that does not hold one yet.

    Re-running moves nothing: the first run clears the source rows, so every later read
    finds no key and skips. That is the whole idempotency guarantee. The destination test
    only stops the patch clobbering a value somebody already set.

    That destination test reads the VALUE and not the presence of the row, because saving
    a Single writes a row for EVERY field including the ones nobody filled. Treating those
    rows as "already set" would skip the carry and strand the values in the source with
    nothing to report.

    ``None`` and ``""`` are the only absences. ``"0"`` is an answer — a ``Check`` the
    operator deliberately cleared — and is never overwritten, so the fold cannot silently
    turn a switch the operator set back on.

    ``frappe.db.get_singles_dict`` is the read, not ``frappe.db.get_value("Singles", …)``:
    that table carries no ``modified`` column for the ORDER BY to name, so the ordinary
    getter raises on it.
    """
    source = frappe.db.get_singles_dict(SOURCE)
    target = frappe.db.get_singles_dict(TARGET)
    for field in FIELDS:
        if field not in source:
            continue
        if target.get(field) not in (None, ""):
            continue
        frappe.db.set_single_value(TARGET, field, source[field])


def _carry_password():
    """Move the gateway API key's ``__Auth`` row, and mirror its display placeholder.

    The destination test decrypts rather than checking for a row, because an operator
    who once saved the field and then cleared it leaves a row with an empty string
    behind (``BaseDocument._save_passwords`` calls ``remove_encrypted_password`` in
    that case, so in practice no row survives a clear — this still reads the value,
    not the row, for the same reason the plain-field carry above does).

    The dummy-asterisk write to ``tabSingles`` is not the secret; it is what
    ``BaseDocument._save_passwords`` itself leaves in the field after every real save,
    and is what the Desk form reads to show the field as configured. Skipping it would
    leave the moved secret invisible in the UI though ``get_password`` would still
    resolve it correctly, because ``BaseDocument.get_password`` falls through to
    ``get_decrypted_password`` whenever the in-memory field is blank.
    """
    secret = get_decrypted_password(SOURCE, SOURCE, PASSWORD_FIELD, raise_exception=False)
    if not secret:
        return
    if get_decrypted_password(TARGET, TARGET, PASSWORD_FIELD, raise_exception=False):
        return
    set_encrypted_password(TARGET, TARGET, secret, PASSWORD_FIELD)
    frappe.db.set_single_value(TARGET, PASSWORD_FIELD, "*" * len(secret))


def _clear_orphan_singles():
    """Delete the source's ``tabSingles`` rows and ``__Auth`` row the DocType deletion
    leaves behind."""
    frappe.db.delete("Singles", {"doctype": SOURCE})
    delete_all_passwords_for(SOURCE, SOURCE)
