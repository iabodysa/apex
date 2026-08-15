# Copyright (c) 2026, AFMCO and contributors
"""WHY THIS FILE IS 2.3x ITS SUBJECT (463 lines against the 201-line
``facility_asset_movement.py``). The subject is not the controller's line count but the
REACHABILITY of the record through the shipped surfaces, and that surface is made of things
the controller does not contain: the DocType's own DocPerm rows, the two workspaces that
link it, the maker/checker split between the role that creates and the role that submits,
the building-scope permission hook, and the ledger the submission posts. Five of those live
outside the 201 lines, so a ratio measured against the controller alone understates the
subject by design. Roughly a third of the file is the fixture chain — two estates, four
rooms, three role-holding users, an asset minted per method — which exists because a
permission verdict is only meaningful against a document that is valid on every OTHER axis;
a shorter fixture would let a link or mandatory failure stand in for the refusal being
asserted. The five methods are five different contracts, not five shapes of one.

Facility Asset Movement is EXECUTABLE: a real housing user can actually create one.

Every pre-existing test for this DocType inserts with ``ignore_permissions=True``
(``test_facility_asset_movement.py``, ``test_facility_asset_movement_effects.py``,
``test_facility_asset_movement_acknowledgement.py``), and the tenant-scope suite drives
``permissions.dual_building_scoped_has_permission`` as a pure function. So the whole
suite was green while NO shipped surface could produce the record: the DocType JSON
granted ``write`` to System Manager / Accommodation Manager / Resident Supervisor but
omitted ``create`` for every role. An omitted DocPerm flag is NOT its DocPerm default —
``frappe.modules.import_file.import_doc`` raises the framework's fixture-import flag
(import_file.py:212) and ``Document._set_defaults`` returns early under it
(document.py:833-835), so the
DocPerm child row never receives ``create``'s default of 1 and ``BaseDocument.get_valid_dict``
writes the Check field as 0 (base_document.py:394-395). Only the Administrator USER could
create a movement (permissions.py:107), which no operator logs in as.

That made two shipped workspace links dead ends: Custody and Safety both link to this
DocType, but the list view's primary "Add" action is gated on ``create``, and there is no
other route — ``facility_asset.js`` adds no custom button, and no whitelisted API builds
one (Facility Asset Delivery writes the shared ledger directly, it does not create a
Movement). This module binds the surface to the permission so the pairing cannot rot:

* ``test_workspace_link_is_backed_by_a_role_that_can_create`` — a workspace that links the
  DocType must grant at least one role that can really create it.
* ``test_in_scope_create_allowed_and_out_of_scope_refused`` — both verdicts in ONE method,
  asserted to DIFFER, so they can never collapse to "everyone is refused" (the state
  before this change) and still pass.
* ``test_unauthorized_role_refused`` — a second, INDEPENDENT refusal mechanism (a
  read-only DocPerm rather than the building-scope hook).
* ``test_submit_posts_exactly_one_ledger_effect`` — counts the ledger before and after,
  globally and per source; "a row exists" would also be true of a double post.
* ``test_cancel_preserves_the_audit_trail`` — asserts what SURVIVES cancellation (the
  original ledger row field-for-field, the cancelled document, its creator attribution),
  not merely that ``cancel()`` returned.

Isolation note: ``FrappeTestCase`` registers its rollback with ``addClassCleanup``
(frappe/tests/utils.py:46), so it fires ONCE PER CLASS and sibling methods see each
other's rows. ``on_submit`` mutates the Facility Asset in place, so the asset is minted
per METHOD; only the immutable fixtures (buildings, rooms, users) are shared.

Field facts verified against the shipped JSON before writing (do NOT guess):
Facility Asset — asset_name/asset_category/naming_series/building/responsible_supervisor
reqd, ``location_in_building`` is a Data field holding a Room name. Room — autoname
``field:room_number``, building + room_number reqd. Facility Asset Movement —
movement_date/facility_asset/movement_category/to_building reqd; ``cancellation_reason``
is ``allow_on_submit``.
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

import apex
from apex.habitat import permissions as P
from apex.tests._helpers import as_user
from apex.tests.factories import make_scoped_supervisor

MOVEMENT = "Facility Asset Movement"
LEDGER = "Facility Asset Movement Ledger"

# The three permlevel-0 writers the controller itself names as the actors that can satisfy
# the intercompany gate (facility_asset_movement.py). Finance Manager and Internal Auditor
# are read-only here BY DESIGN and are deliberately absent.
WRITER_ROLES = ("System Manager", "Accommodation Manager", "Resident Supervisor")

_APP = str(Path(apex.__file__).resolve().parent)
_WORKSPACE_GLOB = os.path.join(_APP, "*", "workspace", "*", "*.json")


def _h():
    return frappe.generate_hash(length=12).upper()


def _workspaces_linking(doctype):
    """title -> granted roles, for every shipped workspace with a DocType link to
    ``doctype``.

    File-level on purpose: a dead workspace link is a property of the shipped JSON, so it
    has to be catchable from the tree that writes it, not only from a migrated site.
    """
    found = {}
    for path in sorted(glob.glob(_WORKSPACE_GLOB)):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if any(
            row.get("link_type") == "DocType" and row.get("link_to") == doctype
            for row in data.get("links") or []
        ):
            title = data.get("title") or data.get("name")
            found[title] = {row["role"] for row in data.get("roles") or [] if row.get("role")}
    return found


class TestFacilityAssetMovementReachability(FrappeTestCase):
    """The shipped creation route works for the role it is shipped for, and only for it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        # Two estates: the supervisor is permitted on `b_in` only, so `b_out` exercises the
        # scope refusal with a doc that is otherwise perfectly valid.
        cls.b_in = cls._building()
        cls.b_out = cls._building()
        cls.room_from = cls._room(cls.b_in)
        cls.room_to = cls._room(cls.b_in)
        cls.room_out_from = cls._room(cls.b_out)
        cls.room_out_to = cls._room(cls.b_out)
        # Never submitted (its every create is refused), so it cannot drift between methods.
        cls.asset_out = cls._asset(cls.b_out, cls.room_out_from)

        cls.supervisor = make_scoped_supervisor(cls._user, cls.b_in, cls.addClassCleanup)
        cls.manager = cls._user("Accommodation Manager")
        # Finance Manager ships an explicit all-zero DocPerm row on this DocType: read and
        # report only. It is the persona for "holds a role on the record but may not write".
        cls.outsider = cls._user("Finance Manager")

    def setUp(self):
        # frappe.session.user is a PROCESS GLOBAL that the row rollback does not restore.
        # Pin it before and after every method so a refusal cannot leak a half-switched
        # session into the next test.
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        # Minted per METHOD: on_submit rewrites this asset's building/location/movement_count
        # and the class-scoped rollback would not undo that between sibling methods.
        self.asset_in = self._asset(self.b_in, self.room_from)

    @classmethod
    def _building(cls):
        doc = frappe.get_doc({"doctype": "Building", "building_name": "REACH-" + _h()})
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        return doc.name

    @classmethod
    def _room(cls, building):
        doc = frappe.get_doc(
            {"doctype": "Room", "building": building, "room_number": "REACH-R-" + _h()}
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        return doc.name

    @classmethod
    def _asset(cls, building, room):
        doc = frappe.get_doc(
            {
                "doctype": "Facility Asset",
                "naming_series": "FAC-AST-.YYYY.-.####",
                "asset_name": "REACH Asset " + _h(),
                "asset_category": "Other",
                "building": building,
                # Data field carrying a Room name; _reconcile_origin resolves from_room
                # from it, so the movement's origin must match what is seeded here.
                "location_in_building": room,
                "responsible_supervisor": "Administrator",
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        return doc.name

    @classmethod
    def _user(cls, role):
        email = "reach-{0}@example.com".format(_h()).lower()
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Reach",
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(frappe.delete_doc, "User", email, force=True, ignore_permissions=True)
        return email

    def _payload(self, asset, from_building, from_room, to_building, to_room):
        """A movement that is VALID on every non-permission axis, so a refusal can only
        be the permission gate: the origin matches the asset and the destination differs."""
        return {
            "doctype": MOVEMENT,
            "movement_date": today(),
            "facility_asset": asset,
            "movement_category": "Same-Company Relocation",
            "from_building": from_building,
            "from_room": from_room,
            "to_building": to_building,
            "to_room": to_room,
        }

    def _in_scope_payload(self):
        return self._payload(self.asset_in, self.b_in, self.room_from, self.b_in, self.room_to)

    def _out_of_scope_payload(self):
        return self._payload(
            self.asset_out, self.b_out, self.room_out_from, self.b_out, self.room_out_to
        )

    def _create_as(self, user, payload):
        """Insert through the REAL permission path (no ignore_permissions) as ``user``."""
        with as_user(user):
            return frappe.get_doc(payload).insert()

    # ---- clause 0: the shipped route exists and a role behind it can use it ----

    def test_workspace_link_is_backed_by_a_role_that_can_create(self):
        """A workspace link to a DocType nobody on that workspace can create is a dead
        end: the list view opens and its primary Add action never renders.

        RED before this change: Custody and Safety both linked the DocType and neither
        granted a single role holding ``create``, because no role held it at all.
        """
        linking = _workspaces_linking(MOVEMENT)
        self.assertTrue(
            linking,
            "no shipped workspace links %s at all — the record would be unreachable "
            "even with perfect DocPerms" % MOVEMENT,
        )

        meta = frappe.get_meta(MOVEMENT)
        creators = {p.role for p in meta.permissions if not p.permlevel and p.create}
        self.assertTrue(
            creators,
            "%s grants `create` to NO role on this site, so its every surface is a dead "
            "end. Shipped DocPerms: %s"
            % (MOVEMENT, sorted({p.role for p in meta.permissions})),
        )

        for title, roles in sorted(linking.items()):
            self.assertTrue(
                roles & creators,
                "workspace %r links %s but grants no role that can create it "
                "(workspace roles=%s, creator roles=%s)"
                % (title, MOVEMENT, sorted(roles), sorted(creators)),
            )

        # The creator set is the controller's own three permlevel-0 writers, and the two
        # read-only personas must never drift into it.
        self.assertEqual(
            creators,
            set(WRITER_ROLES),
            "the roles that may CREATE a movement must stay exactly the permlevel-0 "
            "writers; Finance Manager and Internal Auditor are read-only here by design",
        )

    # ---- clauses 1 + 2: allowed and refused, asserted as one non-collapsing pair ----

    def test_in_scope_create_allowed_and_out_of_scope_refused(self):
        """The authorised in-scope supervisor CAN create; the SAME supervisor CANNOT
        create between two estates they hold no User Permission for.

        Both verdicts are produced in one method and asserted to DIFFER. That is the
        point: in the state shipped before this change (``create`` absent for every role)
        both sides refused, so a refusal-only test was green while the feature was unusable.
        """
        allowed_doc = self._create_as(self.supervisor, self._in_scope_payload())
        self.assertTrue(allowed_doc.name, "in-scope supervisor must get a named draft")
        self.assertEqual(allowed_doc.docstatus, 0)
        # Prove it reached the database rather than only the in-memory document, and that
        # authorship is recorded against the real operator.
        self.assertTrue(frappe.db.exists(MOVEMENT, allowed_doc.name))
        self.assertEqual(
            frappe.db.get_value(MOVEMENT, allowed_doc.name, "owner"), self.supervisor
        )

        before = frappe.db.count(MOVEMENT)
        # frappe.PermissionError by NAME. A link or mandatory failure raises
        # ValidationError instead, and check_permission("create") runs at
        # document.py:300 — before run_before_save_methods — so a validation error
        # cannot stand in for the permission refusal being asserted here.
        with self.assertRaises(frappe.PermissionError):
            self._create_as(self.supervisor, self._out_of_scope_payload())
        self.assertEqual(
            frappe.db.count(MOVEMENT),
            before,
            "a refused create must not leave a row behind",
        )

        # The anti-collapse clause: the two verdicts must be different values.
        in_scope_verdict = frappe.has_permission(
            MOVEMENT,
            "create",
            doc=frappe.get_doc(self._in_scope_payload()),
            user=self.supervisor,
            throw=False,
        )
        out_of_scope_verdict = frappe.has_permission(
            MOVEMENT,
            "create",
            doc=frappe.get_doc(self._out_of_scope_payload()),
            user=self.supervisor,
            throw=False,
        )
        self.assertTrue(in_scope_verdict, "in-scope supervisor must be permitted to create")
        self.assertFalse(out_of_scope_verdict, "out-of-estate create must be refused")
        self.assertNotEqual(
            bool(in_scope_verdict),
            bool(out_of_scope_verdict),
            "allowed and refused collapsed to the same verdict — the pair proves nothing",
        )

    def test_unauthorized_role_refused(self):
        """A second, independent refusal axis: Finance Manager is IN scope everywhere (an
        unscoped oversight role, so the building hook defers) yet still cannot create,
        because its DocPerm row is read/report only. This keeps a refusal proof alive even
        if the scope hook is ever changed."""
        before = frappe.db.count(MOVEMENT)
        with self.assertRaises(frappe.PermissionError):
            self._create_as(self.outsider, self._in_scope_payload())
        self.assertEqual(frappe.db.count(MOVEMENT), before)

        # ...and the refusal is the DocPerm, not the scope hook: the hook defers (None),
        # which frappe reads as "no opinion" (has_controller_permissions, permissions.py:456).
        self.assertIsNone(
            P.building_scoped_has_permission(
                frappe.get_doc(self._in_scope_payload()), "create", user=self.outsider
            ),
            "Finance Manager is an unscoped role, so the building hook must defer — "
            "proving the refusal above came from the read-only DocPerm",
        )

    # ---- clause 3: submission posts EXACTLY ONE ledger effect ----

    def test_submit_posts_exactly_one_ledger_effect(self):
        """Count the ledger before and after. "A row exists" is also true of a double
        post, and the engine carries an idempotency key precisely because a double post
        was possible."""
        movement = self._create_as(self.supervisor, self._in_scope_payload())

        # The supervisor initiates but may not submit — submission is the manager's gate.
        self.assertFalse(
            frappe.has_permission(
                MOVEMENT, "submit", doc=movement, user=self.supervisor, throw=False
            ),
            "Resident Supervisor holds no submit DocPerm; the maker/checker split is the "
            "reason the manager submits below",
        )

        total_before = frappe.db.count(LEDGER)
        source_before = frappe.db.count(
            LEDGER, {"source_doctype": MOVEMENT, "source_name": movement.name}
        )
        self.assertEqual(source_before, 0, "a draft must post nothing")

        with as_user(self.manager):
            frappe.get_doc(MOVEMENT, movement.name).submit()

        self.assertEqual(
            frappe.db.count(LEDGER) - total_before,
            1,
            "submission must post EXACTLY one ledger row app-wide, not zero and not two",
        )
        rows = frappe.get_all(
            LEDGER,
            filters={"source_doctype": MOVEMENT, "source_name": movement.name},
            fields=["name", "from_building", "to_building", "reversal_of", "is_cancelled"],
        )
        self.assertEqual(len(rows), 1, "exactly one ledger row for this source")
        self.assertEqual(rows[0].from_building, self.b_in)
        self.assertEqual(rows[0].to_building, self.b_in)
        self.assertFalse(rows[0].reversal_of, "the posting row is an original, not a reversal")
        self.assertFalse(rows[0].is_cancelled)

    # ---- clause 4: cancellation preserves the audit trail ----

    def test_cancel_preserves_the_audit_trail(self):
        """Assert what SURVIVES the cancellation, not that ``cancel()`` returned.

        The original ledger row must still be there, unedited, alongside exactly one
        negated reversal; the movement document itself must survive as docstatus 2 with
        its reason and its original creator intact.
        """
        movement = self._create_as(self.supervisor, self._in_scope_payload())
        with as_user(self.manager):
            frappe.get_doc(MOVEMENT, movement.name).submit()

        posted = frappe.get_all(
            LEDGER,
            filters={"source_doctype": MOVEMENT, "source_name": movement.name},
            fields=["name", "from_building", "to_building", "from_location", "to_location"],
        )
        self.assertEqual(len(posted), 1)
        original = posted[0]
        total_before = frappe.db.count(LEDGER)

        # cancellation_reason is allow_on_submit, but a save() after submit would re-run
        # validate() -> _reconcile_origin against an asset that has ALREADY moved, which
        # throws. db_set is the shipped pattern for landing it (see the sibling effects
        # test), and the subject here is cancellation, not the reason's own write path.
        frappe.db.set_value(
            MOVEMENT, movement.name, "cancellation_reason", "Reachability audit-trail check"
        )
        with as_user(self.manager):
            frappe.get_doc(MOVEMENT, movement.name).cancel()

        # 1. The source document survives — cancelled, not deleted, reason retained, and
        #    still attributed to the supervisor who initiated it.
        self.assertTrue(
            frappe.db.exists(MOVEMENT, movement.name),
            "cancellation must not delete the movement — the record IS the audit trail",
        )
        survivor = frappe.db.get_value(
            MOVEMENT,
            movement.name,
            ["docstatus", "cancellation_reason", "owner", "from_building", "to_building"],
            as_dict=True,
        )
        self.assertEqual(survivor.docstatus, 2)
        self.assertEqual(survivor.cancellation_reason, "Reachability audit-trail check")
        self.assertEqual(
            survivor.owner,
            self.supervisor,
            "the initiating supervisor must remain recorded as the creator after cancel",
        )
        self.assertEqual(survivor.from_building, self.b_in)
        self.assertEqual(survivor.to_building, self.b_in)

        # 2. The ORIGINAL ledger row survives field-for-field — the reversal is a NEW row,
        #    never an edit of the posting it reverses.
        self.assertTrue(frappe.db.exists(LEDGER, original.name))
        kept = frappe.db.get_value(
            LEDGER,
            original.name,
            [
                "from_building",
                "to_building",
                "from_location",
                "to_location",
                "is_cancelled",
                "reversal_of",
            ],
            as_dict=True,
        )
        self.assertEqual(kept.from_building, original.from_building)
        self.assertEqual(kept.to_building, original.to_building)
        self.assertEqual(kept.from_location, original.from_location)
        self.assertEqual(kept.to_location, original.to_location)
        self.assertFalse(kept.is_cancelled, "the original posting must not be restamped")
        self.assertFalse(kept.reversal_of, "the original posting must not become a reversal")

        # 3. Exactly one reversal was added, and it points back at the original.
        self.assertEqual(
            frappe.db.count(LEDGER) - total_before,
            1,
            "cancellation must post EXACTLY one reversal row",
        )
        reversals = frappe.get_all(
            LEDGER,
            filters={
                "source_doctype": MOVEMENT,
                "source_name": movement.name,
                "reversal_of": ["is", "set"],
            },
            fields=["name", "reversal_of", "is_cancelled", "from_building", "to_building"],
        )
        self.assertEqual(len(reversals), 1)
        self.assertEqual(reversals[0].reversal_of, original.name)
        self.assertTrue(reversals[0].is_cancelled)
