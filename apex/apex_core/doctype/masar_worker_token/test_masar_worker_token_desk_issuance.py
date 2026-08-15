# Copyright (c) 2026, afmcoltd
"""Desk issuance and revocation of the Driver Portal barcode.

What makes this surface different from an ordinary desk action: a driver has no
Frappe account and no password. They scan a barcode, and the raw token in that
barcode IS their identity to every driver-portal endpoint. So the desk button is
not "showing a record" — it is minting a bearer credential, and the button beside
it is the only way to take one back before an off-boarding event does it
automatically.

Every case here asserts a PAIR in one method: the authorised, in-scope action
lands AND the unauthorised or ineligible one is refused. Split across two methods
they can both rot into the same verdict — a refusal that refuses everyone reads
green next to a success that was never re-run. Held together, a collapse in
either direction fails.

The refusals are asserted by MESSAGE, not by exception class alone: the framework
raises PermissionError from the link check and from a dozen other places before a
controller is reached, so ``assertRaises(PermissionError)`` on its own can be
satisfied by a failure that has nothing to do with the rule under test.

FIXTURES, AND WHY THEY ARE NOT MINTED PER METHOD ANY MORE. This file used to insert a
Salis Driver, one or two Users and up to two Projects for every method. Users are the
expensive one: frappe refuses a User insert once 60 have been created in the last hour
(``throttle_user_creation``), so a suite that mints identities per method eventually fails
with "Throttled" for reasons that have nothing to do with what it tests. The drivers are now
apex's own ``_Test Driver`` / ``_Test Driver Two`` fixtures, the issuers are stable
get-or-create identities keyed by the scope they hold, and the two projects are named rather
than tagged so they are created once and reused.

FrappeTestCase rolls back rows once per CLASS, not per method, so everything a method writes
onto a SHARED fixture — the driver's project and status, the credential row itself — is
handed back explicitly in that method rather than left to a rollback that has not happened.

The two classes take DIFFERENT fixture drivers on purpose: the audit class opens by asserting
its driver has no Activity Log rows at all, which only holds for a subject the revocation
class never touched.
"""

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

import apex
from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    TOKEN_TTL_DAYS,
    _hash_token,
    issue_driver_link,
    resolve_driver_token,
    revoke_driver_link,
)
from apex.apex_core.utils.portal_identity import DRIVER
from apex.tests._helpers import _grant_project, _user, as_user
from apex.tests.factories import make_project

test_dependencies = ["Salis Driver"]

TOKEN_DOCTYPE = "Masar Worker Token"
TOKEN_JSON = Path(apex.__file__).resolve().parent / "apex_core" / "doctype" / "masar_worker_token" / "masar_worker_token.json"

# The four roles ISSUER_ROLES grants driver-credential authority to. Each may issue;
# none may read the stored hash, which is a permlevel-1 field.
DRIVER_ISSUER_ROLES = (
    "System Manager",
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
)


# Two named, idempotent tenants: the scope cases need an in-scope and an out-of-scope
# project, and a tagged name would mint a new Project on every run.
PROJECT_MINE = "A267 Project Mine"
PROJECT_THEIRS = "A267 Project Theirs"

# Issuer identities keyed by the authority they hold, so a stable address never accumulates
# a scope another case relies on NOT having.
ISSUERS = {
    ("Fleet Supervisor", PROJECT_MINE): "a267_sup_mine@example.com",
    ("Fleet Supervisor", PROJECT_THEIRS): "a267_sup_theirs@example.com",
    ("Fleet Manager", None): "a267_fleet_manager@example.com",
    ("Accommodation Manager", None): "a267_housing@example.com",
}


class _DeskIssuanceCase(FrappeTestCase):
    """Fixture plumbing for a desk-issuance case."""

    #: Which shipped driver this class acts on. Overridden per class, never shared.
    DRIVER = "_Test Driver"

    def setUp(self):
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        # The shipped DocPerms are the subject of these tests, but a long-lived site
        # can carry hand-edited rows; pin the meta to the JSON this repo ships and
        # put the site's own back afterwards.
        meta = frappe.get_meta(TOKEN_DOCTYPE)
        self._meta_permissions = meta.permissions
        self._meta_autoname = meta.autoname
        self.addCleanup(self._restore_meta)
        meta.permissions = [
            frappe._dict(row) for row in self.shipped_metadata()["permissions"]
        ]
        meta.autoname = "hash"

    def _restore_meta(self):
        meta = frappe.get_meta(TOKEN_DOCTYPE)
        meta.permissions = self._meta_permissions
        meta.autoname = self._meta_autoname

    @staticmethod
    def shipped_metadata():
        return json.loads(TOKEN_JSON.read_text(encoding="utf-8"))

    def _project(self, name):
        return make_project(name)

    def _driver(self, project=None, status="Active"):
        """This class's shipped Salis Driver: no User, no Employee.

        The shared driver factories build a User+Employee+Driver chain, which is the
        opposite of the subject here — the whole point of the barcode is a driver with no
        account at all, which is exactly what ``test_records.json`` ships.

        Its project, its status and any credential it acquires are handed back, because the
        row outlives the method.
        """
        name = frappe.db.get_value("Salis Driver", {"full_name": self.DRIVER})
        self.addCleanup(self._drop_token, name)
        for fieldname, value in (("project", project), ("status", status)):
            self.addCleanup(
                frappe.db.set_value,
                "Salis Driver",
                name,
                fieldname,
                frappe.db.get_value("Salis Driver", name, fieldname),
            )
            frappe.db.set_value("Salis Driver", name, fieldname, value)
        return name

    @staticmethod
    def _drop_token(driver):
        row = frappe.db.get_value(TOKEN_DOCTYPE, {"driver": driver, "holder_type": DRIVER})
        if row:
            frappe.delete_doc(TOKEN_DOCTYPE, row, force=True, ignore_permissions=True)

    def _issuer(self, role, project=None):
        """``project`` is the tenant LABEL; the User Permission needs the autonamed id, so
        the label is resolved through the same idempotent get-or-create the cases use."""
        user = _user(ISSUERS[(role, project)], role)
        if project:
            _grant_project(user, self._project(project))
        return user

    def _token_row(self, driver):
        return frappe.db.get_value(
            TOKEN_DOCTYPE, {"driver": driver, "holder_type": DRIVER}, "name"
        )

    def _assert_link_dead(self, raw, note):
        with self.assertRaises(frappe.PermissionError) as error:
            resolve_driver_token(raw)
        self.assertIn("invalid or inactive", str(error.exception), note)

    def _audit_rows(self, driver):
        return frappe.get_all(
            "Activity Log",
            filters={"link_doctype": "Salis Driver", "link_name": driver},
            fields=["name", "user", "subject", "reference_doctype", "reference_name"],
            order_by="creation asc",
        )


class TestDriverLinkDeskRevocation(_DeskIssuanceCase):
    def test_out_of_scope_supervisor_cannot_revoke_while_the_owning_one_can(self):
        """Project scope narrows revocation exactly as it narrows issuance.

        Without the scope check, a Fleet Supervisor holding one project could
        blank every driver's barcode in the fleet — a quiet, total denial of
        service on the portal, from a role deliberately given only one project.

        The refusal is proved to be REAL by re-resolving the link afterwards: a
        revocation that threw but still disabled the row would satisfy an
        assertRaises on its own."""
        self._project(PROJECT_MINE)
        theirs = self._project(PROJECT_THEIRS)
        outsider = self._issuer("Fleet Supervisor", project=PROJECT_MINE)
        owner = self._issuer("Fleet Supervisor", project=PROJECT_THEIRS)
        driver = self._driver(project=theirs)

        with as_user(owner):
            raw = issue_driver_link(driver)["token"]
        self.assertEqual(resolve_driver_token(raw), driver)

        with as_user(outsider), self.assertRaises(frappe.PermissionError) as refused:
            revoke_driver_link(driver)
        self.assertIn("allowed Project", str(refused.exception))
        self.assertEqual(
            resolve_driver_token(raw),
            driver,
            "the refused revocation must not have disabled anything",
        )

        with as_user(owner):
            result = revoke_driver_link(driver)
        self.assertEqual(result["revoked"], 1)
        self._assert_link_dead(raw, "the owning supervisor's revocation must land")

    def test_a_role_outside_the_fleet_cannot_revoke_a_driver_link(self):
        """Write permission on the token doctype is NOT authority over drivers.

        Housing and HR roles hold write on Masar Worker Token because they issue
        the worker credential from the same record. The doctype check alone would
        therefore let an Accommodation Manager revoke any driver's barcode."""
        driver = self._driver()
        housing = self._issuer("Accommodation Manager")
        fleet = self._issuer("Fleet Manager")

        with as_user(fleet):
            raw = issue_driver_link(driver)["token"]

        with as_user(housing), self.assertRaises(frappe.PermissionError) as refused:
            revoke_driver_link(driver)
        self.assertIn("not permitted to issue", str(refused.exception))
        self.assertEqual(resolve_driver_token(raw), driver)

        with as_user(fleet):
            self.assertEqual(revoke_driver_link(driver)["revoked"], 1)
        self._assert_link_dead(raw, "a fleet manager's revocation must land")

    def test_a_released_driver_can_be_revoked_but_never_issued(self):
        """The two directions must part company once a driver is no longer Active.

        Issuance to a cleared, suspended or released driver has to be refused —
        that is the whole point of revoking on clearance. Revocation must stay
        REACHABLE for exactly the same driver, because a released driver is the
        normal state at the moment an operator reaches for the kill switch, and a
        gate that demands Active would disarm it precisely then.

        The status is written with db.set_value, which runs no document events
        (frappe/database/database.py:942), so the automatic revocation hook does
        not fire and this exercises the manual desk path alone."""
        driver = self._driver()
        fleet = self._issuer("Fleet Manager")

        with as_user(fleet):
            raw = issue_driver_link(driver)["token"]
        self.assertEqual(resolve_driver_token(raw), driver)

        frappe.db.set_value("Salis Driver", driver, "status", "Released")
        self.assertEqual(
            frappe.db.get_value(TOKEN_DOCTYPE, self._token_row(driver), "enabled"),
            1,
            "fixture sanity: the raw status write must not have auto-revoked",
        )

        with as_user(fleet), self.assertRaises(frappe.PermissionError) as refused:
            issue_driver_link(driver)
        self.assertIn("not permitted to issue", str(refused.exception))

        with as_user(fleet):
            self.assertEqual(revoke_driver_link(driver)["revoked"], 1)
        self.assertEqual(
            frappe.db.get_value(TOKEN_DOCTYPE, self._token_row(driver), "enabled"), 0
        )

    def test_revocation_is_idempotent_and_the_old_barcode_never_comes_back(self):
        """What the withdrawn link can still do — the question the card asks last.

        A second revocation must report 0 rather than throw, so an operator who
        clicks twice is not told something failed. And a later re-issue must mint a
        DIFFERENT credential: if reactivation restored the same token, every copy
        of the old QR — printed, forwarded, photographed — would come back to life
        with it."""
        driver = self._driver()
        fleet = self._issuer("Fleet Manager")

        with as_user(fleet):
            first = issue_driver_link(driver)["token"]
            self.assertEqual(revoke_driver_link(driver)["revoked"], 1)
            self.assertEqual(revoke_driver_link(driver)["revoked"], 0)
        self._assert_link_dead(first, "a revoked barcode must stay dead")

        with as_user(fleet):
            second = issue_driver_link(driver)["token"]

        self.assertNotEqual(second, first)
        self.assertEqual(resolve_driver_token(second), driver)
        self._assert_link_dead(first, "re-issuing must not revive the old barcode")

    def test_a_desk_issued_link_expires_and_stays_revocable_once_it_has(self):
        """An expiry that is stamped but not enforced is decoration.

        Both halves are asserted together: the freshly issued link carries a future
        expiry AND resolves, then the same link is refused the moment that expiry
        is in the past. The revocation afterwards proves an expired-but-enabled row
        is still withdrawable, so a lapsed link cannot be left enabled and
        forgotten in the table."""
        driver = self._driver()
        fleet = self._issuer("Fleet Manager")

        with as_user(fleet):
            issued = issue_driver_link(driver)
        raw = issued["token"]

        expires_on = frappe.utils.get_datetime(issued["expires_on"])
        self.assertGreater(expires_on, frappe.utils.now_datetime())
        self.assertLessEqual(
            expires_on,
            frappe.utils.add_to_date(frappe.utils.now_datetime(), days=TOKEN_TTL_DAYS),
        )
        self.assertEqual(resolve_driver_token(raw), driver)

        frappe.db.set_value(
            TOKEN_DOCTYPE,
            self._token_row(driver),
            "expires_on",
            frappe.utils.add_to_date(frappe.utils.now_datetime(), days=-1),
            update_modified=False,
        )
        self._assert_link_dead(raw, "an expired barcode must be refused on use")

        with as_user(fleet):
            self.assertEqual(revoke_driver_link(driver)["revoked"], 1)


class TestDriverLinkIssuanceAudit(_DeskIssuanceCase):
    # The second shipped driver: this class opens by asserting an EMPTY audit trail, which
    # only holds for a subject the revocation class above never issued against.
    DRIVER = "_Test Driver Two"

    def test_every_desk_move_is_audited_by_actor_and_subject(self):
        """An issuance nobody can attribute is an issuance nobody can investigate.

        The token row keeps one ``last_generated_by`` slot, overwritten by the next
        action, and revocation writes with update_modified=False — so before this
        card the record could not say who had held a live credential when. Each of
        the three moves must leave its own row naming the acting user, the token
        record and the driver, and the three subjects must differ so a re-share is
        distinguishable from a rotation."""
        driver = self._driver()
        fleet = self._issuer("Fleet Manager")
        self.assertEqual(self._audit_rows(driver), [])

        with as_user(fleet):
            issue_driver_link(driver)
            issue_driver_link(driver, regenerate=1)
            revoke_driver_link(driver)

        rows = self._audit_rows(driver)
        token_row = self._token_row(driver)
        self.assertGreaterEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row.user, fleet)
            self.assertEqual(row.reference_doctype, TOKEN_DOCTYPE)
            self.assertEqual(row.reference_name, token_row)
            self.assertIn(driver, row.subject)
        self.assertGreaterEqual(
            len({row.subject for row in rows}),
            3,
            "issue, rotate and revoke must be distinguishable in the trail",
        )

    def test_the_audit_trail_never_records_the_credential_itself(self):
        """The trail is the one place a token could be re-read long after issuance.

        Activity Log rows outlive the link and are exportable. Neither the raw
        token nor its stored hash may appear in ANY field of any row — and the
        desk revocation payload must not carry one either, since it is returned to
        a browser that has no reason to receive a credential.

        Asserted beside a positive count so the scan cannot pass by finding
        nothing: the rows exist, and none of them holds the secret."""
        driver = self._driver()
        fleet = self._issuer("Fleet Manager")

        with as_user(fleet):
            first = issue_driver_link(driver)["token"]
            second = issue_driver_link(driver, regenerate=1)["token"]
            revoked = revoke_driver_link(driver)

        secrets = {first, second, _hash_token(first), _hash_token(second)}
        self.assertNotIn(None, secrets)

        rows = frappe.get_all(
            "Activity Log",
            filters={"reference_doctype": TOKEN_DOCTYPE},
            fields=["*"],
        )
        self.assertTrue(rows, "the trail must exist before it can be judged clean")
        haystack = json.dumps(rows, default=str)
        for secret in secrets:
            self.assertNotIn(secret, haystack, "a credential leaked into the audit trail")

        self.assertNotIn("token", revoked)
        for secret in secrets:
            self.assertNotIn(secret, json.dumps(revoked, default=str))

    def test_the_fleet_issuer_can_mint_a_link_but_never_read_a_stored_one(self):
        """Issuing authority is not reading authority.

        Every driver issuer role must be able to act, and none of them may hold the
        permlevel-1 rows that expose the stored hash, nor export/email rights that
        would carry a token record off the site. Paired with the System Manager row
        so the negative assertions cannot pass on an empty permission scan."""
        permissions = self.shipped_metadata()["permissions"]
        base = {row["role"]: row for row in permissions if not row.get("permlevel")}
        elevated = {
            row["role"] for row in permissions if row.get("permlevel") == 1 and row.get("read")
        }

        self.assertIn("System Manager", elevated)
        for role in DRIVER_ISSUER_ROLES:
            self.assertTrue(base[role]["write"], f"{role} must be able to issue")
            if role == "System Manager":
                continue
            self.assertNotIn(role, elevated, f"{role} must not read the stored hash")
            self.assertFalse(base[role].get("export"), f"{role} must not export tokens")
            self.assertFalse(base[role].get("email"), f"{role} must not email tokens")
