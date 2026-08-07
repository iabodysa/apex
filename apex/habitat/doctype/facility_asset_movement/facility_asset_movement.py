# Copyright (c) 2026, AFMCO and contributors
"""Facility Asset Movement controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

from apex.habitat.asset_movement_engine import (
    ensure_asset_still_at,
    ledgered_origin,
    post_asset_movement,
    restore_asset_audit_trail,
    reverse_asset_movement,
)


class FacilityAssetMovement(Document):
    pass


def validate(doc, method=None):
    _reconcile_origin(doc)
    _populate_company_fields(doc)
    _detect_intercompany(doc)

    if doc.from_building == doc.to_building and doc.from_room == doc.to_room:
        frappe.throw(_("From and To location must differ for a Facility Asset Movement."))

    if doc.is_intercompany:
        _validate_intercompany_gates(doc)


def on_submit(doc, method=None):
    """Actually move the asset: snapshot its current location into previous_*, set the
    new building/location from this movement, and bump the movement audit fields.

    The previous code wrote ``current_building``/``current_room``, which do NOT exist
    on Facility Asset (its fields are ``building``/``location_in_building``), so the
    guarded ``updates`` dict stayed empty — every movement was a silent no-op and the
    audit fields (previous_*/movement_count/last_movement_date) never populated."""
    asset = frappe.db.get_value(
        "Facility Asset",
        doc.facility_asset,
        ["building", "location_in_building", "movement_count"],
        as_dict=True,
    )
    if not asset:
        return
    post_asset_movement(
        frappe._dict(
            doctype=doc.doctype,
            name=doc.name,
            facility_asset=doc.facility_asset,
            from_building=doc.from_building,
            from_room=asset.location_in_building or doc.from_room,
            to_building=doc.to_building,
            to_room=doc.to_room,
            from_company=doc.from_company,
            to_company=doc.to_company,
        )
    )
    frappe.db.set_value("Facility Asset", doc.facility_asset, {
        "previous_building": asset.building,
        "previous_location_in_building": asset.location_in_building,
        "building": doc.to_building,
        "location_in_building": doc.to_room,
        "movement_count": (asset.movement_count or 0) + 1,
        "last_movement_date": today(),
    })


def on_cancel(doc, method=None):
    """Revert the asset to where it came from when a submitted movement is cancelled,
    and re-derive the audit trail from the movements that still stand.

    The room comes from this movement's own ledger row, not from ``from_room``: the
    Link cannot hold an origin that is not a Room record, so restoring from it blanked
    the location of any asset delivered to a free-text room. The ledger keeps the room
    the asset really left (Data), which is how Facility Asset Delivery.on_cancel
    already restores its own origin.

    Safe to restore the origin unconditionally because ``before_cancel`` has already
    refused any cancel whose asset no longer sits where this movement left it."""
    origin = ledgered_origin(doc.doctype, doc.name)
    reverse_asset_movement(doc.doctype, doc.name)
    if not frappe.db.exists("Facility Asset", doc.facility_asset):
        return
    count = frappe.db.get_value("Facility Asset", doc.facility_asset, "movement_count") or 0
    frappe.db.set_value("Facility Asset", doc.facility_asset, {
        "building": doc.from_building,
        "location_in_building": origin.from_location if origin else doc.from_room,
        "movement_count": max(0, count - 1),
    })
    restore_asset_audit_trail(doc.facility_asset)


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is required before cancelling a Facility Asset Movement."))
    ensure_asset_still_at(
        doc.facility_asset,
        building=doc.to_building,
        location_in_building=doc.to_room,
    )


def _reconcile_origin(doc):
    """The origin is hand-entered and can drift from where the asset actually is.
    Default blank from_* from the asset's recorded location, and reject a hand-entered
    origin that contradicts it so the move can't start from a phantom location."""
    if not doc.facility_asset:
        return
    asset = frappe.db.get_value(
        "Facility Asset",
        doc.facility_asset,
        ["building", "location_in_building"],
        as_dict=True,
    )
    if not asset:
        return
    if not doc.from_building:
        doc.from_building = asset.building
    elif asset.building and doc.from_building != asset.building:
        frappe.throw(
            _("From Building does not match the asset's current location ({0}).").format(asset.building)
        )
    asset_room = asset.location_in_building
    if asset_room and not frappe.db.exists("Room", asset_room):
        asset_room = None
    if not doc.from_room:
        doc.from_room = asset_room
    elif asset_room and doc.from_room != asset_room:
        frappe.throw(
            _("From Room does not match the asset's current location ({0}).").format(asset_room)
        )


def _populate_company_fields(doc):
    if doc.from_building and not doc.from_company:
        doc.from_company = frappe.db.get_value("Building", doc.from_building, "company") or None
    if doc.to_building and not doc.to_company:
        doc.to_company = frappe.db.get_value("Building", doc.to_building, "company") or None


def _detect_intercompany(doc):
    if doc.from_company and doc.to_company and doc.from_company != doc.to_company:
        doc.is_intercompany = 1
    else:
        doc.is_intercompany = 0


def _validate_intercompany_gates(doc):
    """Block intercompany submissions without release approval and receiving confirmation."""
    if not doc.release_approved_by:
        frappe.throw(_("Release Approved By is required for intercompany asset movement."))
    if not doc.receiving_confirmed_by:
        frappe.throw(_("Receiving Confirmed By is required for intercompany asset movement."))
    if doc.movement_category == "Intercompany Permanent" and not doc.accounting_acknowledged:
        frappe.throw(
            _("Accounting Acknowledged is required before submitting a permanent intercompany transfer.")
        )


ACCOUNTING_ROLE = "Finance Manager"


@frappe.whitelist(methods=["POST"])
def acknowledge_intercompany_movement(movement: str) -> dict:
    """Record Accounting's sign-off on a submitted intercompany movement.

    The two fields sit at permlevel 1 with only Finance Manager holding write there, so
    the desk cannot offer them to a preparer; this is the one path that sets them, and it
    stamps WHO signed in the same call as the flag. Before this existed the flag had no
    allow_on_submit, so a movement submitted without it could never acquire it and the
    pending-acknowledgement card only ever counted up.

    Two refusals are what make it a control rather than a checkbox: a caller without the
    role, and the movement's own submitter. A sign-off the submitter can give themselves
    records nothing.
    """
    doc = frappe.get_doc("Facility Asset Movement", movement)

    if ACCOUNTING_ROLE not in frappe.get_roles():
        frappe.throw(
            _("Only {0} can record the accounting acknowledgement.").format(_(ACCOUNTING_ROLE)),
            frappe.PermissionError,
        )
    if doc.docstatus != 1:
        frappe.throw(_("Only a submitted movement can be acknowledged."))
    if not doc.is_intercompany:
        frappe.throw(_("Only an intercompany movement needs an accounting acknowledgement."))
    if doc.owner == frappe.session.user:
        frappe.throw(
            _("You submitted this movement, so you cannot acknowledge it yourself."),
            frappe.PermissionError,
        )
    if doc.accounting_acknowledged:
        return {"movement": doc.name, "acknowledged_by": doc.accounting_acknowledged_by}

    doc.db_set(
        {"accounting_acknowledged": 1, "accounting_acknowledged_by": frappe.session.user},
        update_modified=True,
    )
    return {"movement": doc.name, "acknowledged_by": frappe.session.user}
