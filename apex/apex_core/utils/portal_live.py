# Copyright (c) 2026, afmcoltd
"""Doorbells for the portals: one event says a subject changed, the page refetches.

Two rooms, because two audiences are admitted on different terms.

``frappe.publish_realtime`` (frappe/realtime.py:23) picks the room from what it is
given, and the trap is what it does with ``doctype=`` alone: only ``list_update``
and ``docinfo_update`` are rewritten to a doctype room, so any other event passing a
doctype WITHOUT a docname falls through to :158 ``get_site_room()`` and is delivered
to the room ``"all"`` — which every System User joins unconditionally at
frappe/realtime/handlers/frappe_handlers.js:12, with no permission check of any kind.
A caller that means "tell the people who may read this doctype" and writes
``doctype=`` alone therefore tells the whole desk instead, and never reaches a portal
Guest, who is not in that room at all.

Both helpers here name their room outright, so neither can fall through:

``notify_building`` rings ``doc:Building/<name>`` — the room a client joins by
emitting ``doc_subscribe``, which the server gates on
``frappe.has_permission(doctype, doc=docname, throw=True)`` before the join
(frappe_handlers.js:47-57). The event is the framework's own ``doc_update``, the
same one ``Document.notify_update`` emits (frappe/model/document.py:1224), so a
portal page needs one listener for every building-scoped change.

``notify_doctype`` rings ``doctype:<doctype>`` — joined by emitting
``doctype_subscribe``, gated on read permission for the doctype
(frappe_handlers.js:19-27). This is the room an operations BOARD wants: it watches
every row of one doctype, not one document.

The payload is a doorbell, never a record: it carries the subject the listener
already knows it is watching, so nothing about a rider, a resident or a session
user crosses the socket. The page refetches through its own permission-scoped
endpoint and learns only what it may read.

Every publish is ``after_commit``, so a listener is never told about a row the
transaction later rolls back.
"""

from __future__ import annotations

import frappe
from frappe.realtime import get_doctype_room


def notify_building(building: str | None) -> bool:
    """Ring one building's watchers. Returns whether a room was rung.

    A blank building is dropped rather than published: with no docname
    ``publish_realtime`` would route the event to the site room and hand a
    building's change to every System User on the site.
    """
    if not building:
        return False
    frappe.publish_realtime(
        "doc_update",
        {"doctype": "Building", "name": building},
        doctype="Building",
        docname=building,
        after_commit=True,
    )
    return True


def notify_doctype(doctype: str, event: str, message: dict | None = None) -> bool:
    """Ring the board watching one doctype. Returns whether a room was rung.

    ``room=`` is passed explicitly because ``doctype=`` alone does not mean the
    doctype room for any event but ``list_update`` — see this module's docstring.
    """
    if not doctype:
        return False
    frappe.publish_realtime(
        event,
        message or {},
        room=get_doctype_room(doctype),
        after_commit=True,
    )
    return True
