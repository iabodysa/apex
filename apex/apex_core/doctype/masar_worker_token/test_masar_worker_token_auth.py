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
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

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
from apex.salis.api import masar

test_dependencies = ["Employee", "Salis Driver", "User"]

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
        being driven as a brute-force / enumeration oracle. The decorator wraps the function
        via functools.wraps and stashes ``__wrapped__``; a missing throttle leaves that
        attribute absent."""
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
            self.assertTrue(
                hasattr(fn, "__wrapped__"),
                f"{fn.__name__} must be wrapped by @rate_limit (brute-force throttle)",
            )

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
