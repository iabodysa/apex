# Copyright (c) 2026, afmcoltd

import frappe

from apex.habitat.temporary_worker_engine import _repoint_party


def execute():
    """Re-point the party columns PARTY_DOCTYPES was extended to cover
    (temporary_worker_engine.py:32-48).

    ``PARTY_DOCTYPES`` listed ten of the twelve doctypes that carry party_type/party;
    Accommodation Stock Ledger and Custody Acknowledgment were missing, so every worker
    already stamped ``Linked`` has source documents naming an Employee while his custody
    BALANCE still names the Temporary Worker. That balance is unreachable: the checkout
    clearance gate reads the Employee leg and clears a resident who is still holding goods,
    and a Custody Return posts against a holder whose balance is zero and is refused.

    Replays the engine's own re-point over every linked worker. The ten doctypes it already
    handled have no rows left matching the Temporary Worker, so the pass is idempotent.
    """
    if not frappe.db.table_exists("Temporary Worker"):
        return

    for tw in frappe.get_all(
        "Temporary Worker",
        filters={"status": "Linked", "linked_employee": ["is", "set"]},
        fields=["name", "linked_employee"],
    ):
        _repoint_party(tw.name, tw.linked_employee)
