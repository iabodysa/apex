# Copyright (c) 2026, afmcoltd

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
    _carry_values()
    _carry_password()

    if frappe.db.exists("DocType", SOURCE):
        frappe.delete_doc("DocType", SOURCE, force=True)

    _clear_orphan_singles()


def _carry_values():
    source = frappe.db.get_singles_dict(SOURCE)
    target = frappe.db.get_singles_dict(TARGET)
    for field in FIELDS:
        if field not in source:
            continue
        if target.get(field) not in (None, ""):
            continue
        frappe.db.set_single_value(TARGET, field, source[field])


def _carry_password():
    secret = get_decrypted_password(SOURCE, SOURCE, PASSWORD_FIELD, raise_exception=False)
    if not secret:
        return
    if get_decrypted_password(TARGET, TARGET, PASSWORD_FIELD, raise_exception=False):
        return
    set_encrypted_password(TARGET, TARGET, secret, PASSWORD_FIELD)
    frappe.db.set_single_value(TARGET, PASSWORD_FIELD, "*" * len(secret))


def _clear_orphan_singles():
    frappe.db.delete("Singles", {"doctype": SOURCE})
    delete_all_passwords_for(SOURCE, SOURCE)
