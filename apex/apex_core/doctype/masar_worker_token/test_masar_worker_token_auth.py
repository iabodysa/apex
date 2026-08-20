# Copyright (c) 2026, afmcoltd
"""Authorization boundary of the Masar worker self-service guest API.

``_resolve_worker`` (salis/api/masar.py) is the SOLE authorization for every
``allow_guest=True`` worker endpoint — get_worker_context / _accommodation / _transport /
list_worker_requests / create_worker_request. The unauthenticated client never supplies an
Employee id, so the personal token is the only thing scoping data to one worker. If that
resolver ever failed open (a blank, unknown, disabled, or inactive-worker token resolving to
a real Employee) or its scope widened, every worker's accommodation, transport and
profile/iqama/passport data would leak to an anonymous URL with no desk login.

FIXTURES, AND WHY THEY ARE NOT OPTIONAL HERE. Six classes each carried a private
``_company()`` and a private ``_make_employee()``, minting an Employee (and one or two
Users) per test method. That is not only duplication: frappe refuses a User insert once 60
have been created in the last hour (``throttle_user_creation``,
frappe/core/doctype/user/user.py), so a suite that mints identities per method starts
failing with "Throttled" for reasons that have nothing to do with what it tests — which is
exactly how this file failed the first time it was actually run. Every identity below is now
an upstream fixture: ERPNext's three ``_Test Employee`` rows, apex's two ``_Test Driver``
rows, frappe's four unprivileged ``test*@example.com`` Users. Not one User is inserted.

WHAT IS STILL BUILT, because it IS the subject: the credential rows themselves, and the
Temporary Worker the employee-only decision refuses to mint one for. ``employee`` and
``driver`` are unique on Masar Worker Token and ``FrappeTestCase`` rolls back per CLASS, so
each case drops the row it minted instead of waiting for a rollback that has not happened.

WHY SOME CASES TAKE A DIFFERENT FIXTURE EMPLOYEE. Notification Log rows are not rolled back
between methods of one class, so the iqama cases each take their own worker; otherwise the
"no HR row exists yet" precondition would read the previous case's row.

TWO CLASSES COLOCATED HERE FOR THE SAME REASON. The hash-at-rest tests (inside
``TestMasarWorkerTokenAuth``, below the audience-scope tests) prove the token column
never holds the raw value and reuse ``_TokenCase.mint``/``.worker()`` unchanged — the
exact fixture shape their own file used to build by hand. ``TestMasarIdentityContract``
proves the worker/driver audience-exclusivity contract against ``portal_identity``
directly, entirely under mocks; it needs no fixture at all, so it colocates for topic
rather than plumbing.
"""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.password import decrypt

from apex.apex_core.doctype.masar_worker_token import masar_worker_token as token_module
from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    _disable_legacy_driver_user,
    _hash_token,
    get_or_create_for_employee,
    issue_driver_link,
    issue_worker_link,
    resolve_driver_token,
    revoke_driver_tokens,
)
from apex.apex_core.utils import portal_identity as security
from apex.salis.api import masar
import inspect
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import apex
from apex.apex_core.doctype.masar_worker_token import masar_worker_token
from apex.apex_core.utils.portal_identity import hash_token
from apex.tests._helpers import _user
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


BLOCKED_STATUSES = ("Inactive", "Suspended", "Left")
TOKEN_DOCTYPE = "Masar Worker Token"

# ERPNext ships exactly three workers; apex ships two drivers; frappe ships the four
# unprivileged Users. Indexed rather than named at the call site so a case that needs "a
# different one from the one next door" says so.
FIXTURE_WORKERS = ("_Test Employee", "_Test Employee 1", "_Test Employee 2")
FIXTURE_DRIVER = "_Test Driver"
LEGACY_WEBSITE_USER = "test1@example.com"
LEGACY_SYSTEM_USER = "test2@example.com"
HR_ENABLED_USER = "test3@example.com"
HR_DISABLED_USER = "test4@example.com"


class _TokenCase(FrappeTestCase):
    """Fixture plumbing shared by every class in this file — one copy, not six."""

    def setUp(self):
        # Registered first so a mid-test failure still hands the next case an
        # Administrator session.
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")

    def worker(self, index=0):
        """One of ERPNext's fixture Employees, by position."""
        return frappe.db.get_value("Employee", {"first_name": FIXTURE_WORKERS[index]})

    def driver(self):
        return frappe.db.get_value("Salis Driver", {"full_name": FIXTURE_DRIVER})

    def drop_token(self, name):
        """Idempotent: a case may drop its row mid-body and still register this cleanup."""
        if name and frappe.db.exists(TOKEN_DOCTYPE, name):
            frappe.delete_doc(TOKEN_DOCTYPE, name, force=True, ignore_permissions=True)

    def borrow(self, doctype, name, fieldname, value):
        """Set a field on a SHARED fixture row and hand the old value back afterwards."""
        self.addCleanup(
            frappe.db.set_value,
            doctype,
            name,
            fieldname,
            frappe.db.get_value(doctype, name, fieldname),
        )
        frappe.db.set_value(doctype, name, fieldname, value)

    def mint(self, employee, enabled=1):
        """Insert a worker credential for ``employee`` and drop it after the case."""
        doc = frappe.get_doc(
            {
                "doctype": TOKEN_DOCTYPE,
                "party_type": "Employee",
                "party": employee,
                "employee": employee,
                "enabled": enabled,
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(self.drop_token, doc.name)
        return doc


class TestDriverBarcodeCutover(_TokenCase):
    """The driver barcode replaces a Website-User login, and must never touch a real one."""

    def setUp(self):
        super().setUp()
        # A driver token names itself after the driver, so the field-based autoname the
        # worker side uses does not apply; pin the meta and put the site's own back.
        meta = frappe.get_meta(TOKEN_DOCTYPE)
        self.addCleanup(setattr, meta, "autoname", meta.autoname)
        meta.autoname = "hash"

        self.subject = self.driver()
        self.addCleanup(self.drop_token, self.subject)
        self.addCleanup(
            frappe.db.set_value,
            "Salis Driver",
            self.subject,
            {
                "status": frappe.db.get_value("Salis Driver", self.subject, "status"),
                "driver_user": frappe.db.get_value("Salis Driver", self.subject, "driver_user"),
            },
        )

    def _with_legacy_user(self, user, user_type):
        """Borrow a fixture User as the driver's legacy login, at the given user_type."""
        self.borrow("User", user, "user_type", user_type)
        self.borrow("User", user, "enabled", 1)
        frappe.db.set_value("Salis Driver", self.subject, "driver_user", user)
        return user

    def test_issue_disables_legacy_website_user_after_token_is_live(self):
        user = self._with_legacy_user(LEGACY_WEBSITE_USER, "Website User")

        issued = issue_driver_link(self.subject)

        self.assertEqual(resolve_driver_token(issued["token"]), self.subject)
        self.assertEqual(frappe.db.get_value("User", user, "enabled"), 0)

    def test_issue_never_disables_a_system_user(self):
        user = self._with_legacy_user(LEGACY_SYSTEM_USER, "System User")

        issued = issue_driver_link(self.subject)

        self.assertEqual(resolve_driver_token(issued["token"]), self.subject)
        self.assertEqual(frappe.db.get_value("User", user, "enabled"), 1)

    def test_expired_barcode_never_disables_the_legacy_user(self):
        user = self._with_legacy_user(LEGACY_WEBSITE_USER, "Website User")
        issue_driver_link(self.subject)
        frappe.db.set_value("User", user, "enabled", 1)
        frappe.db.set_value(
            TOKEN_DOCTYPE,
            self.subject,
            "expires_on",
            frappe.utils.add_to_date(frappe.utils.now_datetime(), days=-1),
        )

        self.assertFalse(_disable_legacy_driver_user(self.subject))
        self.assertEqual(frappe.db.get_value("User", user, "enabled"), 1)

    def test_retiring_the_legacy_login_goes_through_the_user_document(self):
        """The column write left the driver's LIVE session working.

        Only ``User.check_enable_disable`` (frappe/core/doctype/user/user.py:273-280)
        logs an account out, and ``frappe.db.set_value`` never reaches a controller — so
        a driver already signed in on the old portal kept it until the session aged out.
        Mocked rather than run against the site, because the property under test is which
        WRITE PATH is taken, and both paths leave the same ``enabled`` column behind.
        """
        with patch.object(token_module, "frappe") as frappe_mock:
            frappe_mock.db.get_value.side_effect = [
                frappe._dict(token="hashed", expires_on=None),
                "legacy@example.com",
                frappe._dict(enabled=1, user_type="Website User"),
            ]
            frappe_mock.get_roles.return_value = []

            self.assertTrue(_disable_legacy_driver_user("DRV-1"))

            frappe_mock.get_doc.assert_called_once_with("User", "legacy@example.com")
            user_doc = frappe_mock.get_doc.return_value
            self.assertEqual(user_doc.enabled, 0)
            user_doc.save.assert_called_once_with(ignore_permissions=True)
            frappe_mock.db.set_value.assert_not_called()

    def test_reissue_rotates_and_reenables_a_revoked_driver_token(self):
        first = issue_driver_link(self.subject)
        self.assertEqual(revoke_driver_tokens(self.subject), 1)
        with self.assertRaises(frappe.PermissionError):
            resolve_driver_token(first["token"])

        second = issue_driver_link(self.subject)

        self.assertNotEqual(second["token"], first["token"])
        self.assertTrue(second["enabled"])
        self.assertEqual(resolve_driver_token(second["token"]), self.subject)

    def test_released_driver_cannot_be_reissued_until_restored_to_active(self):
        first = issue_driver_link(self.subject)
        revoke_driver_tokens(self.subject)
        frappe.db.set_value("Salis Driver", self.subject, "status", "Released")

        with self.assertRaises(frappe.PermissionError):
            issue_driver_link(self.subject)
        with self.assertRaises(frappe.PermissionError):
            resolve_driver_token(first["token"])

        frappe.db.set_value("Salis Driver", self.subject, "status", "Active")
        second = issue_driver_link(self.subject)
        self.assertEqual(resolve_driver_token(second["token"]), self.subject)


class TestMasarWorkerTokenAuth(_TokenCase):
    def test_token_resolves_to_only_its_own_employee(self):
        """Two workers, two tokens: token A resolves to A and ONLY A — never B. This is the
        anti-leak invariant; if it widened, one worker's link would surface another
        worker's data."""
        emp_a, emp_b = self.worker(0), self.worker(1)
        token_a = self.mint(emp_a)._plaintext_token
        token_b = self.mint(emp_b)._plaintext_token

        self.assertNotEqual(emp_a, emp_b)
        self.assertNotEqual(token_a, token_b)

        self.assertEqual(masar._resolve_worker(token_a), emp_a)
        self.assertNotEqual(masar._resolve_worker(token_a), emp_b)
        self.assertEqual(masar._resolve_worker(token_b), emp_b)

        ctx = masar.get_worker_context(token=token_a)
        self.assertEqual(ctx["employee"], emp_a, "get_worker_context must scope to token's worker")
        self.assertNotEqual(ctx["employee"], emp_b, "must never return the other worker")

    def test_blank_token_is_rejected(self):
        """A blank/missing token must 403, not resolve to anyone (fails closed so a
        truncated /masar link never silently leaks a real worker)."""
        for blank in (None, "", "   "):
            with self.assertRaises(frappe.PermissionError):
                masar._resolve_worker(blank)
            with self.assertRaises(frappe.PermissionError):
                masar.get_worker_context(token=blank)

    def test_unknown_token_is_rejected(self):
        """A well-formed but non-existent token must 403 (no row -> fail closed)."""
        bogus = frappe.generate_hash(length=48)
        self.assertFalse(frappe.db.exists(TOKEN_DOCTYPE, {"token": _hash_token(bogus)}))
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(bogus)
        with self.assertRaises(frappe.PermissionError):
            masar.get_worker_context(token=bogus)

    def test_disabled_token_is_rejected(self):
        """enabled=0 revokes the link: a token whose row exists but is disabled must 403,
        even though its Employee is a real, Active worker."""
        emp = self.worker()
        token = self.mint(emp, enabled=0)._plaintext_token
        self.assertEqual(
            frappe.db.get_value(TOKEN_DOCTYPE, {"employee": emp}, "enabled"),
            0,
            "fixture sanity: token row must be present and disabled",
        )
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(token)
        with self.assertRaises(frappe.PermissionError):
            masar.get_worker_context(token=token)

    def test_inactive_or_left_employee_token_is_rejected(self):
        """An enabled token whose Employee has left/gone inactive must 403 — a departed
        worker's link stops resolving even though the token row is still enabled. Status is
        flipped via a direct DB write so we exercise exactly the Employee.status read
        _resolve_worker performs, without depending on HR's own status-transition rules
        (e.g. a relieving_date requirement).

        The worker is a SHARED fixture and its credential is unique, so each pass through
        the loop returns the status and drops the row before the next one mints.
        """
        emp = self.worker()
        self.addCleanup(frappe.db.set_value, "Employee", emp, "status", "Active")
        for status in BLOCKED_STATUSES:
            with self.subTest(status=status):
                doc = self.mint(emp, enabled=1)
                frappe.db.set_value("Employee", emp, "status", status)
                self.assertEqual(
                    frappe.db.get_value("Employee", emp, "status"),
                    status,
                    f"fixture sanity: employee status must be {status}",
                )
                with self.assertRaises(frappe.PermissionError):
                    masar._resolve_worker(doc._plaintext_token)
                with self.assertRaises(frappe.PermissionError):
                    masar.get_worker_context(token=doc._plaintext_token)
                # Both back before the next pass: issuance refuses a non-Active subject, so
                # a status left behind would break the NEXT mint rather than this assertion.
                self.drop_token(doc.name)
                frappe.db.set_value("Employee", emp, "status", "Active")

    def test_explicit_worker_reissue_rotates_and_reenables_revoked_row(self):
        employee = self.worker()
        self.addCleanup(self.drop_token, employee)
        first = issue_worker_link(employee)
        frappe.db.set_value(
            TOKEN_DOCTYPE, {"holder_type": "Worker", "employee": employee}, "enabled", 0
        )

        second = issue_worker_link(employee)

        self.assertNotEqual(second["token"], first["token"])
        self.assertTrue(second["enabled"])
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(first["token"])
        self.assertEqual(masar._resolve_worker(second["token"]), employee)

    # -- Hashed at rest -- the raw personal token must never be stored in clear: a
    # direct read of the row must expose ZERO usable secret. The row keeps only a
    # SHA-256 hash (what the resolver matches) plus a site-key-encrypted recoverable
    # copy (``token_enc``) so the desk can re-share the SAME link without rotating.

    def test_minted_row_stores_the_hash_not_the_raw_token(self):
        """A minted token exposes the RAW value once (via the controller), but the
        stored ``token`` column is its SHA-256 hash -- the plaintext is absent from the
        row, so a direct DB read leaks no usable secret."""
        doc = self.mint(self.worker())
        raw = doc._plaintext_token
        self.assertTrue(raw, "the raw token must be available once, right after mint")

        stored = frappe.db.get_value(TOKEN_DOCTYPE, doc.name, "token")
        self.assertNotEqual(stored, raw, "the raw token must never be stored in clear")
        self.assertEqual(stored, _hash_token(raw), "the row must store the SHA-256 hash")
        self.assertEqual(len(stored), 64, "a SHA-256 hex digest is 64 chars")

    def test_raw_link_still_resolves_after_hashing(self):
        """The anti-leak contract is preserved: the raw token (the value baked into the
        worker's /masar link) resolves to exactly its own Employee even though the row
        stores only the hash."""
        emp = self.worker()
        doc = self.mint(emp)
        raw = doc._plaintext_token

        self.assertEqual(masar._resolve_worker(raw), emp)
        self.assertEqual(masar.get_worker_context(token=raw)["employee"], emp)
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(doc.token)

    def test_encrypted_copy_round_trips_to_the_raw_token(self):
        """``token_enc`` is a recoverable (site-key) copy so the desk can re-share the
        SAME link without rotating; it decrypts back to the raw, and it is NOT the raw
        in clear (a DB read of it is useless without the site key)."""
        doc = self.mint(self.worker())
        raw = doc._plaintext_token

        enc = frappe.db.get_value(TOKEN_DOCTYPE, doc.name, "token_enc")
        self.assertTrue(enc, "an encrypted recoverable copy must be stored")
        self.assertNotEqual(enc, raw, "the encrypted copy must not equal the raw token")
        self.assertEqual(decrypt(enc), raw, "the encrypted copy must round-trip to the raw")

    def test_issue_worker_link_shows_raw_but_stores_hash(self):
        """The desk issuer returns the RAW token/link (shown once) while the row it
        wrote stores only the hash -- the show-once, hash-at-rest guarantee end to
        end."""
        emp = self.worker()
        res = issue_worker_link(employee=emp)
        self.addCleanup(self.drop_token, emp)
        raw = res["token"]
        self.assertIn(raw, res["link"], "the returned link must carry the raw token")
        self.assertEqual(masar._resolve_worker(raw), emp, "the issued link must resolve")

        stored = frappe.db.get_value(TOKEN_DOCTYPE, {"employee": emp}, "token")
        self.assertEqual(stored, _hash_token(raw), "the row must store only the hash")
        self.assertNotEqual(stored, raw)


class TestMasarWorkerTokenSecurityHardening(_TokenCase):
    """The 2026 token-hardening contract.

    Guards the invariants that must hold after the security pass:
      * an EXPIRED token is refused (fail-closed), while a currently-valid
        (pre-existing) link still resolves, including after the expiry backfill.
      * every guest token-resolution endpoint carries an @rate_limit, so a personal
        link cannot be driven as a brute-force / enumeration oracle.
      * the ``token`` Data field is at permlevel 1, so the low roles that only need
        the row (not the secret) cannot read the token.
    """

    def test_fresh_token_carries_a_future_expiry(self):
        """A minted token gets a future ``expires_on`` (the TTL is stamped on insert), and
        that token resolves to its worker — the happy path is non-vacuous."""
        emp = self.worker()
        doc = self.mint(emp)
        self.assertTrue(doc.expires_on, "a minted token must carry an expiry")
        self.assertGreater(
            frappe.utils.get_datetime(doc.expires_on),
            frappe.utils.now_datetime(),
            "a fresh token's expiry must be in the future",
        )
        self.assertEqual(masar._resolve_worker(doc._plaintext_token), emp)

    def test_expired_token_is_refused(self):
        """A token whose ``expires_on`` is in the past fails closed (PermissionError), even
        though the row exists, is enabled, and points at an Active worker."""
        doc = self.mint(self.worker())
        frappe.db.set_value(
            TOKEN_DOCTYPE,
            doc.name,
            "expires_on",
            frappe.utils.add_to_date(frappe.utils.now_datetime(), days=-1),
            update_modified=False,
        )
        self.assertEqual(frappe.db.get_value(TOKEN_DOCTYPE, doc.name, "enabled"), 1)
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(doc._plaintext_token)
        with self.assertRaises(frappe.PermissionError):
            masar.get_worker_context(token=doc._plaintext_token)

    def test_null_expiry_legacy_token_is_rejected(self):
        """A persisted token without an expiry fails closed until it is backfilled."""
        doc = self.mint(self.worker())
        frappe.db.set_value(
            TOKEN_DOCTYPE, doc.name, "expires_on", None, update_modified=False
        )
        self.assertIsNone(frappe.db.get_value(TOKEN_DOCTYPE, doc.name, "expires_on"))
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(doc._plaintext_token)

    def test_every_guest_worker_endpoint_carries_a_rate_limit(self):
        """Each ``@frappe.whitelist(allow_guest=True)`` worker endpoint that resolves a
        token must also carry an ``@rate_limit`` — the throttle that stops a personal link
        being driven as a brute-force / enumeration oracle.

        ``__wrapped__`` cannot prove this: ``frappe.whitelist`` itself wraps every
        endpoint via ``functools.wraps`` (frappe/utils/typing_validations.py), so
        that attribute is present whether or not ``@rate_limit`` ever ran — a
        whitelisted function with no throttle at all still reports it. Instead this
        asserts ``_apex_rate_limit``, the marker
        ``apex.apex_core.utils.rate_limit_identity.rate_limit`` stamps on its own
        wrapper, which exists only when that decorator does."""
        guest_endpoints = [
            masar.get_enum_labels,
            masar.get_worker_context,
            masar.get_worker_accommodation,
            masar.get_worker_transport,
            masar.list_worker_requests,
            masar.get_worker_request_detail,
            masar.get_worker_custody,
            masar.create_worker_request,
            masar.get_worker_home,
            masar.get_worker_contacts,
            masar.notify_hr_iqama_expiring,
            masar.confirm_boarding,
            masar.get_worker_boarding_pass,
            masar.create_worker_transport_request,
        ]
        for fn in guest_endpoints:
            with self.subTest(endpoint=fn.__name__):
                self.assertTrue(
                    hasattr(fn, "_apex_rate_limit"),
                    f"{fn.__name__} must be wrapped by @rate_limit (brute-force throttle)",
                )

    def test_the_rate_limit_marker_can_actually_fail(self):
        """Negative control for the case above: a whitelisted function with no
        ``@rate_limit`` at all must NOT carry ``_apex_rate_limit`` — proving the
        assertion above can fail, unlike the ``__wrapped__`` check it replaced."""
        self.assertFalse(hasattr(masar.get_my_worker_route_today, "_apex_rate_limit"))

    def test_token_field_is_permlevel_one(self):
        """The ``token`` Data field sits at permlevel 1, so a role without a permlevel-1
        read row never receives the secret in a row read — the low roles lose token
        visibility while keeping the rest of the record."""
        meta = frappe.get_meta(TOKEN_DOCTYPE)
        field = meta.get_field("token")
        self.assertIsNotNone(field, "token field must exist")
        self.assertEqual(field.permlevel, 1, "token must be at permlevel 1")

        high = {p.role for p in meta.permissions if getattr(p, "permlevel", 0) == 1 and p.read}
        # System Manager is the only role with a permlevel-1 read row
        # (masar_worker_token.json:235-238); no housing or fleet role may gain one.
        self.assertEqual(high, {"System Manager"}, "permlevel-1 read must be System Manager alone")
        for low in (
            "Accommodation Manager",
            "Resident Supervisor",
            "HR User",
            "Fleet Supervisor",
            "Fleet Manager",
            "Fleet Project Manager",
        ):
            self.assertNotIn(low, high, f"{low} must NOT have permlevel-1 read on the token field")


class TestMasarTokenTransport(_TokenCase):
    """The httpOnly-cookie transport.

    The SPA no longer carries the raw token in the query string or in the page HTML; it
    rides in the httpOnly ``masar_wt`` cookie and the endpoints read it server-side via
    ``_token_from_request``. An explicit arg still wins (backward-compat with a freshly
    distributed ?w= link and unit-test callers)."""

    class _Req:
        def __init__(self, cookies):
            self.cookies = cookies

    def setUp(self):
        super().setUp()
        self.addCleanup(
            setattr, frappe.local, "request", getattr(frappe.local, "request", None)
        )

    def test_explicit_arg_wins_over_cookie(self):
        frappe.local.request = self._Req({"masar_wt": "from-cookie"})
        self.assertEqual(masar._token_from_request("from-arg"), "from-arg")

    def test_cookie_used_when_no_arg(self):
        frappe.local.request = self._Req({"masar_wt": "from-cookie"})
        self.assertEqual(masar._token_from_request(""), "from-cookie")
        self.assertEqual(masar._token_from_request(None), "from-cookie")

    def test_no_arg_no_cookie_is_empty(self):
        frappe.local.request = self._Req({})
        self.assertEqual(masar._token_from_request(None), "")

    def test_resolver_reads_the_cookie(self):
        """End-to-end: with no token arg, _resolve_worker resolves the worker from the
        cookie alone — the transport the hardened SPA actually uses."""
        emp = self.worker()
        token = self.mint(emp)._plaintext_token
        frappe.local.request = self._Req({"masar_wt": token})
        self.assertEqual(masar._resolve_worker(None), emp)


class TestMasarNotifyHrIqamaExpiring(_TokenCase):
    """The one-tap 'notify HR my Iqama is expiring' contract.

    notify_hr_iqama_expiring re-derives days_left from the Employee record (here the
    ``valid_upto`` Iqama-expiry the resolver already falls back to) and raises a native HR
    Notification Log ONLY inside the action window (``_IQAMA_NOTIFY_HR_LEAD_DAYS`` == 30).
    The window gate is server-side, so a worker comfortably outside 30 days is a silent
    no-op even though the same token happily resolves — the client can never force HR spam
    by faking the threshold.

    Each case takes a DIFFERENT fixture worker: a Notification Log row written by one method
    is still there for the next (the rollback is per class), so sharing one worker would let
    an earlier row satisfy a later precondition.
    """

    def _worker_with_iqama_in(self, index, days_from_today):
        """A fixture Employee whose Iqama (valid_upto) expires ``days_from_today`` days out,
        plus an enabled token. Both the borrowed field and the row are handed back."""
        employee = self.worker(index)
        self.borrow(
            "Employee",
            employee,
            "valid_upto",
            frappe.utils.add_days(frappe.utils.today(), days_from_today),
        )
        return employee, self.mint(employee)._plaintext_token

    def _hr_notifications_for(self, employee):
        """Count HR-targeted Notification Log rows raised for this employee."""
        return frappe.db.count(
            "Notification Log",
            {"document_type": "Employee", "document_name": employee, "type": "Alert"},
        )

    def test_in_window_worker_notifies_hr(self):
        """Iqama 15 days out (<= 30): the endpoint raises a Notification Log to the HR
        inbox, scoped to this worker, and reports notified=True."""
        employee, token = self._worker_with_iqama_in(1, 15)
        self.assertEqual(self._hr_notifications_for(employee), 0)
        self.assertTrue(masar._hr_notify_recipients(), "an HR inbox recipient must exist")

        res = masar.notify_hr_iqama_expiring(token=token)
        self.assertTrue(res["notified"], "an in-window Iqama must notify HR")
        self.assertEqual(res["days_left"], 15)
        self.assertGreaterEqual(res["recipients"], 1)
        self.assertGreaterEqual(
            self._hr_notifications_for(employee), 1, "an HR Notification Log row must exist"
        )

    def test_out_of_window_worker_is_a_noop(self):
        """Iqama 200 days out (> 30): the same token resolves, but the endpoint raises
        NOTHING and reports notified=False — no HR row is created."""
        employee, token = self._worker_with_iqama_in(2, 200)
        self.assertEqual(masar._resolve_worker(token), employee)

        res = masar.notify_hr_iqama_expiring(token=token)
        self.assertFalse(res["notified"], "an out-of-window Iqama must be a no-op")
        self.assertEqual(res["days_left"], 200)
        self.assertEqual(res["recipients"], 0)
        self.assertEqual(
            self._hr_notifications_for(employee), 0, "no HR row may be created out of window"
        )

    def test_blank_token_is_rejected(self):
        """The write endpoint funnels through _resolve_worker, so a blank token fails closed
        (PermissionError) before any notification is considered."""
        with self.assertRaises(frappe.PermissionError):
            masar.notify_hr_iqama_expiring(token="")

    def test_disabled_hr_recipient_is_skipped(self):
        """C2 (bug fix — behaviour IMPROVED, not merely preserved): the notify loop now
        routes through ``notify_user_system``, which carries an enabled-user check the raw
        ``Notification Log`` insert lacked. BEFORE, a disabled HR user still received a row;
        AFTER, only the enabled recipient does. Two recipients (one enabled, one disabled)
        prove the skip while the enabled path still delivers exactly one scoped alert."""
        employee, token = self._worker_with_iqama_in(0, 10)
        enabled_user, disabled_user = HR_ENABLED_USER, HR_DISABLED_USER
        self.borrow("User", enabled_user, "enabled", 1)
        self.borrow("User", disabled_user, "enabled", 0)

        with patch.object(
            masar, "_hr_notify_recipients", return_value=[enabled_user, disabled_user]
        ):
            res = masar.notify_hr_iqama_expiring(token=token)

        self.assertTrue(res["notified"])
        # the enabled recipient receives exactly one row scoped to this worker
        self.assertEqual(
            frappe.db.count(
                "Notification Log", {"for_user": enabled_user, "document_name": employee}
            ),
            1,
        )
        # the disabled recipient receives NONE — the redirect's enabled-check (the fix)
        self.assertEqual(
            frappe.db.count(
                "Notification Log", {"for_user": disabled_user, "document_name": employee}
            ),
            0,
        )


class TestMasarEmployeeOnlyDecision(_TokenCase):
    """Masar Worker credentials bind exclusively to Employee records.

    The Temporary Worker below is built rather than borrowed on purpose: it is the SUBJECT —
    a worker with no Employee record at all — and no fixture ships one.
    """

    def _temporary_worker(self, suffix):
        return frappe.get_doc(
            {
                "doctype": "Temporary Worker",
                "worker_name": f"Temp Worker {self._testMethodName}-{suffix}",
                "passport_number": f"T325-{frappe.generate_hash(length=12)}",
                "arrival_date": frappe.utils.today(),
                "status": "Active",
            }
        ).insert(ignore_permissions=True)

    def test_controller_refuses_to_mint_a_temporary_worker_token(self):
        """The token controller rejects a Temporary-Worker party at save, so no dead Masar
        link can ever be issued for a worker with no Employee."""
        tw = self._temporary_worker("mint")
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(
                {
                    "doctype": TOKEN_DOCTYPE,
                    "party_type": "Temporary Worker",
                    "party": tw.name,
                    "enabled": 1,
                }
            ).insert(ignore_permissions=True)
        self.assertFalse(
            frappe.db.exists(
                TOKEN_DOCTYPE, {"party_type": "Temporary Worker", "party": tw.name}
            ),
            "no Temporary-Worker token row may be created",
        )

    def test_temporary_worker_token_is_rejected_by_exact_binding(self):
        """A persisted Temporary Worker credential cannot satisfy Worker binding."""
        tw = self._temporary_worker("resolve")
        forced_token = frappe.generate_hash(length=48)
        doc = frappe.get_doc(
            {
                "doctype": TOKEN_DOCTYPE,
                "name": tw.name,
                "holder_type": "Worker",
                "party_type": "Temporary Worker",
                "party": tw.name,
                "employee": None,
                "enabled": 1,
                "token": _hash_token(forced_token),
            }
        )
        doc.db_insert()
        self.addCleanup(self.drop_token, tw.name)
        row = frappe.db.get_value(
            TOKEN_DOCTYPE,
            {"token": _hash_token(forced_token)},
            ["holder_type", "party_type", "employee", "enabled"],
            as_dict=True,
        )
        self.assertEqual(row.holder_type, "Worker")
        self.assertEqual(row.party_type, "Temporary Worker")
        self.assertFalse(row.employee, "a temp-worker token carries no employee")
        self.assertEqual(row.enabled, 1)

        with self.assertRaises(frappe.PermissionError) as ctx:
            masar._resolve_worker(forced_token)
        self.assertIn("subject binding is invalid", str(ctx.exception))

        with self.assertRaises(frappe.PermissionError):
            masar.get_worker_context(token=forced_token)


class TestMasarWorkerTokenAutoname(_TokenCase):
    """A token created with ONLY the Employee link must name + validate.

    autoname is ``field:party``, which set_new_name resolves BEFORE before_validate runs. If
    party were derived only in before_validate, a token minted with just the Employee link
    would fail naming with "Worker is required" before it ever reached validation.
    before_insert mirrors employee -> party so naming has it; this is the guard for that
    root-cause fix (the get_or_create_for_employee path passes no party).
    """

    def test_token_with_only_employee_names_and_validates(self):
        """Insert a token supplying ONLY employee (no party / party_type). It must insert,
        autoname to the employee (field:party, party derived from employee), and back-fill
        party_type/party via before_insert's employee -> party mirror
        (masar_worker_token.py:275)."""
        emp = self.worker()
        self.addCleanup(self.drop_token, emp)
        doc = frappe.get_doc({"doctype": TOKEN_DOCTYPE, "employee": emp}).insert(
            ignore_permissions=True
        )
        self.assertEqual(doc.name, emp, "token must autoname to the employee via field:party")
        self.assertEqual(doc.party, emp)
        self.assertEqual(doc.party_type, "Employee")
        self.assertEqual(doc.employee, emp)
        self.assertTrue(doc.token, "a token must be minted on insert")

    def test_get_or_create_for_brand_new_employee_succeeds(self):
        """get_or_create_for_employee inserts {doctype, employee} with no party; it must
        succeed for an Employee with no credential yet and return the named token row."""
        emp = self.worker(1)
        self.addCleanup(self.drop_token, emp)
        self.assertFalse(frappe.db.exists(TOKEN_DOCTYPE, {"employee": emp}))
        doc = get_or_create_for_employee(emp)
        self.assertEqual(doc.employee, emp)
        self.assertEqual(doc.name, emp)
        self.assertEqual(doc.party, emp)
        self.assertTrue(frappe.db.exists(TOKEN_DOCTYPE, {"employee": emp}))
        again = get_or_create_for_employee(emp)
        self.assertEqual(again.name, doc.name)


class TestMasarIdentityContract(TestCase):
    """The worker/driver audience-exclusivity contract, proven under mocks.

    A plain ``TestCase`` on purpose: every case here mocks ``frappe.db`` (or the
    resolver itself) rather than touching the database, so it needs no
    ``test_dependencies`` and no ``FrappeTestCase`` rollback machinery.
    """

    @patch.object(security, "_throttle_bad_token_attempt")
    @patch.object(security.frappe.db, "get_value")
    def test_worker_and_driver_tokens_are_audience_exclusive(
        self, get_value, _throttle
    ):
        get_value.return_value = None

        with self.assertRaises(frappe.PermissionError):
            security.resolve_portal_subject(
                security.DRIVER, "worker-token", required=True
            )

        token_filters = get_value.call_args.args[1]
        self.assertEqual(token_filters["holder_type"], security.DRIVER)
        self.assertEqual(token_filters["enabled"], 1)

    @patch.object(security, "presented_token", return_value=("", False))
    def test_salis_session_is_not_a_driver_bearer_credential(self, _presented):
        self.assertIsNone(resolve_driver_token())

    def test_binding_rejects_mixed_worker_and_driver_subjects(self):
        row = frappe._dict(
            holder_type="Worker",
            party_type="Employee",
            party="EMP-1",
            employee="EMP-1",
            driver="DRV-1",
        )
        with self.assertRaises(frappe.PermissionError):
            security.validate_subject_binding(
                row, security.WORKER, exception=frappe.PermissionError
            )

    @staticmethod
    def _worker_row(expires_on):
        return frappe._dict(
            holder_type="Worker",
            party_type="Employee",
            party="EMP-1",
            employee="EMP-1",
            driver=None,
            expires_on=expires_on,
        )

    @patch.object(security, "_throttle_bad_token_attempt")
    @patch.object(security.frappe.db, "get_value")
    def test_expired_token_fails_closed(self, get_value, _throttle):
        """The two reads answer differently on purpose.

        One ``return_value`` for both made the Employee-status read return the token row,
        which is not "Active" — so the refusal came from the status gate whatever the
        expiry said, and the case passed identically for a token expiring in 2099.
        """
        get_value.side_effect = [self._worker_row("2000-01-01 00:00:00"), "Active"]
        with self.assertRaises(frappe.PermissionError):
            security.resolve_portal_subject(security.WORKER, "expired", required=True)

    @patch.object(security, "_throttle_bad_token_attempt")
    @patch.object(security.frappe.db, "get_value")
    def test_an_unexpired_token_resolves_its_subject(self, get_value, _throttle):
        """The mirror the expiry case needs: same mocks, expiry the only difference."""
        get_value.side_effect = [self._worker_row("2099-01-01 00:00:00"), "Active"]
        self.assertEqual(
            security.resolve_portal_subject(security.WORKER, "live", required=True),
            "EMP-1",
        )

    def test_revocation_disables_the_subjects_notification_devices(self):
        with (
            patch.object(security, "_lock_subject_row", return_value=frappe._dict(name="EMP-1")),
            patch.object(
                security,
                "_lock_subject_token_rows",
                return_value=[frappe._dict(name="TOKEN-1", enabled=1)],
            ),
            patch.object(security, "log_credential_event"),
            patch.object(security.frappe.db, "set_value"),
            patch.object(security.frappe.db, "table_exists", return_value=True),
            patch("apex.salis.api.web_push.disable_subject_subscriptions") as disable,
        ):
            self.assertEqual(security.revoke_subject_tokens(security.WORKER, "EMP-1"), 1)

        disable.assert_called_once_with(security.WORKER, "EMP-1")

test_dependencies = ['Employee', 'Salis Driver', 'User']


# --- merged from test_masar_worker_token_credential_permlevel.py ---
_TOKEN_JSON = (
    Path(apex.__file__).resolve().parent
    / "apex_core"
    / "doctype"
    / "masar_worker_token"
    / "masar_worker_token.json"
)
HOUSING_ROLE = "Accommodation Manager"
PRIVILEGED_ROLE = "System Manager"
CREDENTIAL_FIELDS = ("token", "token_enc")
class TestMasarWorkerTokenCredentialPermlevel(FrappeTestCase):
    """Site-bound. ``frappe.session.user`` is process state that no rollback restores."""

    def setUp(self):
        # Registered BEFORE anything mutates the session, so a mid-test failure still hands
        # the next test an Administrator session.
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")
        self.employee = frappe.db.get_value("Employee", {"first_name": "_Test Employee"})

    def _token(self):
        """An issued credential row. ``before_insert`` always mints, so the row carries a
        real hash and a real ciphertext -- there is nothing to conceal otherwise."""
        name = (
            frappe.get_doc({"doctype": "Masar Worker Token", "employee": self.employee})
            .insert(ignore_permissions=True)
            .name
        )
        self.addCleanup(
            frappe.delete_doc, "Masar Worker Token", name, force=True, ignore_permissions=True
        )
        return name

    def test_housing_role_gets_none_where_system_manager_gets_the_credential(self):
        """THE PAIR. Both verdicts in ONE method so they can never drift apart.

        Split across two methods, a bug that concealed the credential from EVERYBODY would
        satisfy the refusal half and read as correct. The final assertion states the
        difference outright: same document, same two columns, two roles, two outcomes.
        """
        name = self._token()
        housing = _user("cred_housing@example.com", HOUSING_ROLE)
        privileged = _user("cred_privileged@example.com", PRIVILEGED_ROLE)

        # Verdict A -- the withdrawn role receives nothing.
        frappe.set_user(housing)
        stripped = frappe.client.get("Masar Worker Token", name)
        for fieldname in CREDENTIAL_FIELDS:
            self.assertIsNone(
                stripped.get(fieldname), f"{HOUSING_ROLE} can still read {fieldname}"
            )
        self.assertEqual(
            stripped.get("employee"),
            frappe.db.get_value("Masar Worker Token", name, "employee"),
            "a level-0 field was stripped too -- the removal took the whole record",
        )

        # Verdict B -- the retained role still receives the credential. Note this runs as a
        # REAL System Manager, never Administrator: the strip returns early for
        # Administrator and the verdict would be vacuous.
        frappe.set_user(privileged)
        visible = frappe.client.get("Masar Worker Token", name)
        for fieldname in CREDENTIAL_FIELDS:
            self.assertIsNotNone(
                visible.get(fieldname),
                f"{PRIVILEGED_ROLE} lost {fieldname} -- level 1 is now unreachable by anyone",
            )
        self.assertEqual(
            visible.get("token"),
            frappe.db.get_value("Masar Worker Token", name, "token"),
            f"{PRIVILEGED_ROLE} received something other than the stored hash",
        )

        # The pair, stated: the two roles must not have produced the same answer.
        self.assertNotEqual(
            [stripped.get(f) for f in CREDENTIAL_FIELDS],
            [visible.get(f) for f in CREDENTIAL_FIELDS],
            "both roles read the same values -- the permlevel is not being enforced",
        )

    def test_only_system_manager_holds_a_permlevel_one_row(self):
        """The shipped JSON, checked rather than trusted. ``frappe.get_meta`` answers off
        the DATABASE, so a green meta assertion on an un-migrated site would grade the old
        row; this one grades the file that migrate will import."""
        shipped = json.loads(_TOKEN_JSON.read_text(encoding="utf-8"))
        high = {p["role"] for p in shipped["permissions"] if int(p.get("permlevel") or 0) == 1}
        self.assertEqual(
            high,
            {PRIVILEGED_ROLE},
            "the permlevel-1 role set changed -- only System Manager may hold level 1",
        )
        for fieldname in CREDENTIAL_FIELDS:
            field = [f for f in shipped["fields"] if f["fieldname"] == fieldname][0]
            self.assertEqual(
                field.get("permlevel"),
                1,
                f"{fieldname} left permlevel 1 -- the row removal now conceals nothing",
            )

    def test_the_reshare_path_still_hands_the_raw_token_to_a_role_without_level_one(self):
        """WHAT THE PERMLEVEL DOES NOT BUY, proven rather than asserted in prose.

        The row above withholds the stored hash and ciphertext from the housing role. It
        does NOT withhold the credential: ``reshare_worker_link`` returns a link carrying
        the RAW token, because ``authorize_issuance`` gates that path on role and scope and
        never reads a permlevel. Anyone tempted to read the permlevel row as full credential
        protection should fail here first.

        The token itself is never logged or asserted on directly -- only its hash is
        compared, and the stored hash is re-read AFTER the call so the verdict holds on both
        branches of ``recover_token`` (decrypt for an unscoped issuer, rotate for a scoped
        one).
        """
        name = self._token()
        housing = _user("cred_housing@example.com", HOUSING_ROLE)

        frappe.set_user(housing)
        link = masar_worker_token.reshare_worker_link(self.employee)
        self.assertIsNotNone(link, "the issuer got no link at all -- the path changed")

        raw = parse_qs(urlparse(link).query).get("w", [""])[0]
        self.assertTrue(raw, "the link carries no token parameter")
        self.assertEqual(
            hash_token(raw),
            frappe.db.get_value("Masar Worker Token", name, "token"),
            f"{HOUSING_ROLE} received something that is not the live credential",
        )

    def test_the_reshare_docstring_still_names_that_exposure(self):
        """The warning must survive a refactor, so assert it is there.

        A reader who arrives at the permlevel row and stops looking draws the wrong
        conclusion; the docstring on the re-share path is where they are told otherwise.
        Keyed on the two load-bearing words rather than a whole sentence, so rewording is
        free and DELETING the warning is not.
        """
        doc = (inspect.getdoc(masar_worker_token.reshare_worker_link) or "").lower()
        for phrase in ("raw token", "permlevel"):
            self.assertIn(
                phrase,
                doc,
                "reshare_worker_link stopped documenting that every issuer role still "
                f"obtains the raw token there (missing: {phrase!r})",
            )

    def test_the_level_zero_row_survived(self):
        """The explicit non-change. Only a field-level read was withdrawn, not the housing
        role's authority over the record."""
        rows = json.loads(_TOKEN_JSON.read_text(encoding="utf-8"))["permissions"]
        housing = [
            p for p in rows if p["role"] == HOUSING_ROLE and int(p.get("permlevel") or 0) == 0
        ]
        self.assertEqual(len(housing), 1, f"{HOUSING_ROLE} lost or gained a permlevel-0 row")
        for flag in ("read", "write", "create", "print", "report", "share"):
            self.assertEqual(
                housing[0].get(flag),
                1,
                f"{HOUSING_ROLE} permlevel-0 {flag} was collateral damage",
            )


# --- merged from test_masar_worker_token_desk_issuance.py ---
TOKEN_DOCTYPE_masar_worker_token_desk_issuance = "Masar Worker Token"
TOKEN_JSON = Path(apex.__file__).resolve().parent / "apex_core" / "doctype" / "masar_worker_token" / "masar_worker_token.json"
DRIVER_ISSUER_ROLES = (
    "System Manager",
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
)
PROJECT_MINE = "A267 Project Mine"
PROJECT_THEIRS = "A267 Project Theirs"
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
        meta = frappe.get_meta(TOKEN_DOCTYPE_masar_worker_token_desk_issuance)
        self._meta_permissions = meta.permissions
        self._meta_autoname = meta.autoname
        self.addCleanup(self._restore_meta)
        meta.permissions = [
            frappe._dict(row) for row in self.shipped_metadata()["permissions"]
        ]
        meta.autoname = "hash"

    def _restore_meta(self):
        meta = frappe.get_meta(TOKEN_DOCTYPE_masar_worker_token_desk_issuance)
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
        row = frappe.db.get_value(TOKEN_DOCTYPE_masar_worker_token_desk_issuance, {"driver": driver, "holder_type": DRIVER})
        if row:
            frappe.delete_doc(TOKEN_DOCTYPE_masar_worker_token_desk_issuance, row, force=True, ignore_permissions=True)

    def _issuer(self, role, project=None):
        """``project`` is the tenant LABEL; the User Permission needs the autonamed id, so
        the label is resolved through the same idempotent get-or-create the cases use."""
        user = _user(ISSUERS[(role, project)], role)
        if project:
            _grant_project(user, self._project(project))
        return user

    def _token_row(self, driver):
        return frappe.db.get_value(
            TOKEN_DOCTYPE_masar_worker_token_desk_issuance, {"driver": driver, "holder_type": DRIVER}, "name"
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
            frappe.db.get_value(TOKEN_DOCTYPE_masar_worker_token_desk_issuance, self._token_row(driver), "enabled"),
            1,
            "fixture sanity: the raw status write must not have auto-revoked",
        )

        with as_user(fleet), self.assertRaises(frappe.PermissionError) as refused:
            issue_driver_link(driver)
        self.assertIn("not permitted to issue", str(refused.exception))

        with as_user(fleet):
            self.assertEqual(revoke_driver_link(driver)["revoked"], 1)
        self.assertEqual(
            frappe.db.get_value(TOKEN_DOCTYPE_masar_worker_token_desk_issuance, self._token_row(driver), "enabled"), 0
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
            TOKEN_DOCTYPE_masar_worker_token_desk_issuance,
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
            self.assertEqual(row.reference_doctype, TOKEN_DOCTYPE_masar_worker_token_desk_issuance)
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
            filters={"reference_doctype": TOKEN_DOCTYPE_masar_worker_token_desk_issuance},
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


# --- merged from test_masar_worker_token_scope.py ---
def _driver_clause(projects):
    escaped = ", ".join(frappe.db.escape(v) for v in projects)
    return (
        "(`holder_type` = 'Driver' and `driver` in ("
        "select `name` from `tabSalis Driver` where `project` in ({0})))"
    ).format(escaped)
def _worker_clause(buildings):
    escaped = ", ".join(frappe.db.escape(v) for v in buildings)
    return (
        "(`holder_type` = 'Worker' and `employee` in ("
        "select `employee` from `tabHousing Assignment` where `docstatus` = 1 "
        "and `check_out_date` is null and `building` in ({0})))"
    ).format(escaped)
class TestMasarWorkerTokenScopeQuery(TestCase):
    def test_administrator_is_unrestricted(self):
        self.assertEqual(security.masar_worker_token_scope_query(user="Administrator"), "")

    def test_a_role_holding_neither_issuer_set_sees_nothing(self):
        with patch.object(security.frappe, "get_roles", return_value={"Employee"}):
            self.assertEqual(
                security.masar_worker_token_scope_query(user="nobody@example.com"), "1=0"
            )

    def test_fleet_manager_sees_every_driver_row_and_no_worker_row(self):
        with patch.object(security.frappe, "get_roles", return_value={"Fleet Manager"}):
            query = security.masar_worker_token_scope_query(user="fm@example.com")
        self.assertEqual(query, "(`holder_type` = 'Driver')")

    def test_hr_user_sees_every_worker_row_and_no_driver_row(self):
        with patch.object(security.frappe, "get_roles", return_value={"HR User"}):
            query = security.masar_worker_token_scope_query(user="hr@example.com")
        self.assertEqual(query, "(`holder_type` = 'Worker')")

    def test_a_role_in_both_issuer_sets_unions_both_unrestricted_clauses(self):
        with patch.object(security.frappe, "get_roles", return_value={"System Manager"}):
            query = security.masar_worker_token_scope_query(user="sm@example.com")
        self.assertEqual(query, "(`holder_type` = 'Driver' or `holder_type` = 'Worker')")

    def test_fleet_supervisor_is_confined_to_their_projects(self):
        with (
            patch.object(security.frappe, "get_roles", return_value={"Fleet Supervisor"}),
            patch(
                "apex.salis.permissions._allowed_projects",
                return_value=["PROJ-A", "PROJ-B"],
            ),
        ):
            query = security.masar_worker_token_scope_query(user="fs@example.com")
        self.assertEqual(query, "({0})".format(_driver_clause(["PROJ-A", "PROJ-B"])))

    def test_fleet_supervisor_with_no_project_sees_nothing(self):
        with (
            patch.object(security.frappe, "get_roles", return_value={"Fleet Supervisor"}),
            patch("apex.salis.permissions._allowed_projects", return_value=[]),
        ):
            query = security.masar_worker_token_scope_query(user="fs@example.com")
        self.assertEqual(query, "(1=0)")

    def test_resident_supervisor_is_confined_to_their_buildings(self):
        with (
            patch.object(security.frappe, "get_roles", return_value={"Resident Supervisor"}),
            patch("apex.habitat.permissions._allowed_buildings", return_value=["BLD-A"]),
        ):
            query = security.masar_worker_token_scope_query(user="rs@example.com")
        self.assertEqual(query, "({0})".format(_worker_clause(["BLD-A"])))
class TestMasarWorkerTokenHasPermission(TestCase):
    def _doc(self, **fields):
        return frappe._dict(fields)

    def test_a_write_ptype_always_defers_regardless_of_role(self):
        doc = self._doc(holder_type="Driver", driver="DRV-1")
        with patch.object(security.frappe, "get_roles", return_value=set()):
            for ptype in ("write", "create", "delete", "submit"):
                with self.subTest(ptype=ptype):
                    self.assertIsNone(
                        security.masar_worker_token_has_permission(
                            doc, ptype, user="anyone@example.com"
                        )
                    )

    def test_administrator_may_read_everything(self):
        doc = self._doc(holder_type="Worker", employee="EMP-1")
        self.assertIsNone(
            security.masar_worker_token_has_permission(doc, "read", user="Administrator")
        )

    def test_a_role_outside_the_docs_audience_issuer_set_is_denied(self):
        doc = self._doc(holder_type="Worker", employee="EMP-1")
        with patch.object(security.frappe, "get_roles", return_value={"Fleet Manager"}):
            self.assertFalse(
                security.masar_worker_token_has_permission(doc, "read", user="fm@example.com")
            )

    def test_an_unscoped_role_reads_a_row_without_resolving_its_project(self):
        doc = self._doc(holder_type="Driver", driver="DRV-1")
        with (
            patch.object(security.frappe, "get_roles", return_value={"Fleet Manager"}),
            patch.object(security.frappe.db, "get_value") as get_value,
        ):
            self.assertIsNone(
                security.masar_worker_token_has_permission(doc, "read", user="fm@example.com")
            )
        get_value.assert_not_called()

    def test_a_scoped_fleet_supervisor_is_admitted_when_the_drivers_project_is_allowed(self):
        doc = self._doc(holder_type="Driver", driver="DRV-1")
        with (
            patch.object(security.frappe, "get_roles", return_value={"Fleet Supervisor"}),
            patch.object(security.frappe.db, "get_value", return_value="PROJ-A"),
            patch(
                "apex.salis.permissions._allowed_projects",
                return_value=["PROJ-A", "PROJ-B"],
            ),
        ):
            self.assertIsNone(
                security.masar_worker_token_has_permission(doc, "report", user="fs@example.com")
            )

    def test_a_scoped_fleet_supervisor_is_denied_when_the_drivers_project_is_not_allowed(self):
        doc = self._doc(holder_type="Driver", driver="DRV-1")
        with (
            patch.object(security.frappe, "get_roles", return_value={"Fleet Supervisor"}),
            patch.object(security.frappe.db, "get_value", return_value="PROJ-A"),
            patch("apex.salis.permissions._allowed_projects", return_value=["PROJ-B"]),
        ):
            self.assertFalse(
                security.masar_worker_token_has_permission(doc, "print", user="fs@example.com")
            )

    def test_a_resident_supervisor_is_admitted_when_every_live_building_is_allowed(self):
        doc = self._doc(holder_type="Worker", employee="EMP-1")
        with (
            patch.object(security.frappe, "get_roles", return_value={"Resident Supervisor"}),
            patch.object(security.frappe, "get_all", return_value=["BLD-A"]),
            patch(
                "apex.habitat.permissions._allowed_buildings",
                return_value=["BLD-A", "BLD-B"],
            ),
        ):
            self.assertIsNone(
                security.masar_worker_token_has_permission(doc, "read", user="rs@example.com")
            )

    def test_a_resident_supervisor_is_denied_when_a_live_building_is_not_allowed(self):
        doc = self._doc(holder_type="Worker", employee="EMP-1")
        with (
            patch.object(security.frappe, "get_roles", return_value={"Resident Supervisor"}),
            patch.object(security.frappe, "get_all", return_value=["BLD-A", "BLD-C"]),
            patch("apex.habitat.permissions._allowed_buildings", return_value=["BLD-A"]),
        ):
            self.assertFalse(
                security.masar_worker_token_has_permission(doc, "read", user="rs@example.com")
            )

    def test_a_worker_doc_with_no_employee_link_is_denied_without_a_lookup(self):
        doc = self._doc(holder_type="Worker", employee=None)
        with (
            patch.object(security.frappe, "get_roles", return_value={"Resident Supervisor"}),
            patch.object(security.frappe, "get_all") as get_all,
        ):
            self.assertFalse(
                security.masar_worker_token_has_permission(doc, "read", user="rs@example.com")
            )
        get_all.assert_not_called()
