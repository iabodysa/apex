# Copyright (c) 2026, AFMCO and contributors
"""Authorization boundary of the Masar worker self-service guest API.

``_resolve_worker`` (salis/api/masar.py) is the SOLE authorization for every
``allow_guest=True`` worker endpoint — get_worker_context / _accommodation /
_transport / list_worker_requests / create_worker_request. The unauthenticated
client never supplies an Employee id, so the personal token is the only thing
scoping data to one worker. If that resolver ever failed open (a blank, unknown,
disabled, or inactive-worker token resolving to a real Employee) or its scope
widened, every worker's accommodation, transport and profile/iqama/passport data
would leak to an anonymous URL with no desk login. No existing test calls these
endpoints, so this file is the guard for that fail-closed contract.

These cases (token -> exactly one Employee; blank/unknown/disabled/inactive ->
PermissionError) are verified against the live resolver and the public
get_worker_context endpoint on a migrated site with no production data.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    _disable_legacy_driver_user,
    _hash_token,
    get_or_create_for_employee,
    issue_driver_link,
    resolve_driver_token,
    revoke_driver_tokens,
)
from apex.salis.api import masar
from apex.tests._helpers import _user

# [#bwkatw]
BLOCKED_STATUSES = ("Inactive", "Left")


class TestDriverBarcodeCutover(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._token_meta = frappe.get_meta("Masar Worker Token")
        self._original_autoname = self._token_meta.autoname
        self._token_meta.autoname = "hash"

    def tearDown(self):
        self._token_meta.autoname = self._original_autoname
        frappe.set_user("Administrator")

    def _driver(self, user_type=None):
        tag = frappe.generate_hash(length=12).lower()
        user = None
        if user_type:
            user = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": f"barcode-{tag}@example.com",
                    "first_name": f"Barcode {tag}",
                    "enabled": 1,
                    "send_welcome_email": 0,
                }
            ).insert(ignore_permissions=True).name
            frappe.db.set_value("User", user, "user_type", user_type)

        driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": f"Barcode Driver {tag}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name
        if user:
            frappe.db.set_value("Salis Driver", driver, "driver_user", user)
        return driver, user

    def test_issue_disables_legacy_website_user_after_token_is_live(self):
        driver, user = self._driver("Website User")

        issued = issue_driver_link(driver)

        self.assertEqual(resolve_driver_token(issued["token"]), driver)
        self.assertEqual(frappe.db.get_value("User", user, "enabled"), 0)

    def test_issue_never_disables_a_system_user(self):
        driver, user = self._driver("System User")

        issued = issue_driver_link(driver)

        self.assertEqual(resolve_driver_token(issued["token"]), driver)
        self.assertEqual(frappe.db.get_value("User", user, "enabled"), 1)

    def test_expired_barcode_never_disables_the_legacy_user(self):
        driver, user = self._driver("Website User")
        issue_driver_link(driver)
        frappe.db.set_value("User", user, "enabled", 1)
        frappe.db.set_value(
            "Masar Worker Token",
            driver,
            "expires_on",
            frappe.utils.add_to_date(frappe.utils.now_datetime(), days=-1),
        )

        self.assertFalse(_disable_legacy_driver_user(driver))
        self.assertEqual(frappe.db.get_value("User", user, "enabled"), 1)

    def test_reissue_rotates_and_reenables_a_revoked_driver_token(self):
        driver, _user_name = self._driver()
        first = issue_driver_link(driver)
        self.assertEqual(revoke_driver_tokens(driver), 1)
        self.assertIsNone(resolve_driver_token(first["token"]))

        second = issue_driver_link(driver)

        self.assertNotEqual(second["token"], first["token"])
        self.assertTrue(second["enabled"])
        self.assertEqual(resolve_driver_token(second["token"]), driver)

    def test_released_driver_cannot_be_reissued_until_restored_to_active(self):
        driver, _user_name = self._driver()
        first = issue_driver_link(driver)
        revoke_driver_tokens(driver)
        frappe.db.set_value("Salis Driver", driver, "status", "Released")

        with self.assertRaises(frappe.ValidationError):
            issue_driver_link(driver)
        self.assertIsNone(resolve_driver_token(first["token"]))

        frappe.db.set_value("Salis Driver", driver, "status", "Active")
        second = issue_driver_link(driver)
        self.assertEqual(resolve_driver_token(second["token"]), driver)


class TestMasarWorkerTokenAuth(FrappeTestCase):
    def setUp(self):
        # [#6tz8cy]
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    # [#kjq1ae]

    def _company(self):
        """A usable Company on this site (global default, else any)."""
        return (
            frappe.defaults.get_global_default("company")
            or frappe.get_all("Company", limit=1)[0].name
        )

    def _make_employee(self, suffix, status="Active"):
        """Insert one Employee, unique per test+suffix, with the minimal HR fields
        the suite already relies on (see tests/factories.make_employee)."""
        tag = f"{self._testMethodName}-{suffix}"
        return (
            frappe.get_doc(
                {
                    "doctype": "Employee",
                    "first_name": f"Masar Worker {tag}",
                    "company": self._company(),
                    "status": status,
                    "gender": "Male",
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": "2020-01-01",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _make_token(self, employee, enabled=1):
        """Issue a Masar Worker Token for ``employee`` and return its minted RAW token
        string. The token is stored hashed (P-104), so the raw value is available only
        transiently on the freshly minted doc (``_plaintext_token``)."""
        doc = frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                # [#627eic]
                "party_type": "Employee",
                "party": employee,
                "employee": employee,
                "enabled": enabled,
            }
        ).insert(ignore_permissions=True)
        self.assertTrue(doc.token, "fixture sanity: a token must be minted on insert")
        self.assertEqual(doc.employee, employee, "fixture sanity: token bound to the employee")
        return doc._plaintext_token

    # [#50ls4h]

    def test_token_resolves_to_only_its_own_employee(self):
        """Two seeded workers, two tokens: token A resolves to A and ONLY A —
        never B. This is the anti-leak invariant; if it widened, one worker's link
        would surface another worker's data."""
        emp_a = self._make_employee("a")
        emp_b = self._make_employee("b")
        token_a = self._make_token(emp_a)
        token_b = self._make_token(emp_b)

        # [#5idrd4]
        self.assertNotEqual(emp_a, emp_b)
        self.assertNotEqual(token_a, token_b)

        # [#munz7x]
        self.assertEqual(masar._resolve_worker(token_a), emp_a)
        self.assertNotEqual(masar._resolve_worker(token_a), emp_b)
        self.assertEqual(masar._resolve_worker(token_b), emp_b)

        # [#m2u9u0]
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
        # [#601y4f]
        self.assertFalse(frappe.db.exists("Masar Worker Token", {"token": _hash_token(bogus)}))
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(bogus)
        with self.assertRaises(frappe.PermissionError):
            masar.get_worker_context(token=bogus)

    def test_disabled_token_is_rejected(self):
        """enabled=0 revokes the link: a token whose row exists but is disabled must
        403, even though its Employee is a real, Active worker."""
        emp = self._make_employee("disabled")
        token = self._make_token(emp, enabled=0)
        # [#azg80h]
        self.assertEqual(
            frappe.db.get_value("Masar Worker Token", {"employee": emp}, "enabled"),
            0,
            "fixture sanity: token row must be present and disabled",
        )
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(token)
        with self.assertRaises(frappe.PermissionError):
            masar.get_worker_context(token=token)

    def test_inactive_or_left_employee_token_is_rejected(self):
        """An enabled token whose Employee has left/gone inactive must 403 — a
        departed worker's link stops resolving even though the token row is still
        enabled. Status is flipped via a direct DB write so we exercise exactly the
        Employee.status read _resolve_worker performs, without depending on HR's
        own status-transition rules (e.g. a relieving_date requirement)."""
        for status in BLOCKED_STATUSES:
            emp = self._make_employee(status.lower())
            token = self._make_token(emp, enabled=1)
            frappe.db.set_value("Employee", emp, "status", status)
            # [#gm5t3b]
            self.assertEqual(
                frappe.db.get_value("Employee", emp, "status"),
                status,
                f"fixture sanity: employee status must be {status}",
            )
            with self.assertRaises(frappe.PermissionError):
                masar._resolve_worker(token)
            with self.assertRaises(frappe.PermissionError):
                masar.get_worker_context(token=token)


class TestMasarWorkerTokenSecurityHardening(FrappeTestCase):
    """The 2026 token-hardening contract (T-628/629/660/662/672/685/705).

    Guards the four invariants that must hold after the security pass:
      * T-629 — an EXPIRED token is refused (fail-closed), while a currently-valid
        (pre-existing) link still resolves, including after the expiry backfill.
      * T-628 — every guest token-resolution endpoint carries an @rate_limit, so a
        personal link cannot be driven as a brute-force / enumeration oracle.
      * T-662 — the ``token`` Data field is at permlevel 1, so the low roles that
        only need the row (not the secret) cannot read the token.
    """

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _company(self):
        return (
            frappe.defaults.get_global_default("company")
            or frappe.get_all("Company", limit=1)[0].name
        )

    def _worker(self, suffix):
        tag = f"{self._testMethodName}-{suffix}"
        return (
            frappe.get_doc(
                {
                    "doctype": "Employee",
                    "first_name": f"Masar Sec {tag}",
                    "company": self._company(),
                    "status": "Active",
                    "gender": "Male",
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": "2020-01-01",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _token_doc(self, employee):
        return frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "party_type": "Employee",
                "party": employee,
                "employee": employee,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)

    # [#rtd33z]

    def test_fresh_token_carries_a_future_expiry(self):
        """A minted token gets a future ``expires_on`` (the TTL is stamped on insert),
        and that token resolves to its worker — the happy path is non-vacuous."""
        emp = self._worker("fresh")
        doc = self._token_doc(emp)
        self.assertTrue(doc.expires_on, "a minted token must carry an expiry")
        self.assertGreater(
            frappe.utils.get_datetime(doc.expires_on),
            frappe.utils.now_datetime(),
            "a fresh token's expiry must be in the future",
        )
        # [#qx3e71]
        self.assertEqual(masar._resolve_worker(doc._plaintext_token), emp)

    def test_expired_token_is_refused(self):
        """A token whose ``expires_on`` is in the past fails closed (PermissionError),
        even though the row exists, is enabled, and points at an Active worker."""
        emp = self._worker("expired")
        doc = self._token_doc(emp)
        # [#dpfkek]
        frappe.db.set_value(
            "Masar Worker Token",
            doc.name,
            "expires_on",
            frappe.utils.add_to_date(frappe.utils.now_datetime(), days=-1),
            update_modified=False,
        )
        # [#c52dtf]
        self.assertEqual(frappe.db.get_value("Masar Worker Token", doc.name, "enabled"), 1)
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(doc._plaintext_token)
        with self.assertRaises(frappe.PermissionError):
            masar.get_worker_context(token=doc._plaintext_token)

    def test_null_expiry_legacy_token_still_resolves(self):
        """A legacy row with a NULL expiry (minted before the field existed, not yet
        backfilled) must NOT be treated as expired — it resolves, the deliberate
        backward-compat seam that keeps live links working until the backfill runs."""
        emp = self._worker("legacy")
        doc = self._token_doc(emp)
        frappe.db.set_value(
            "Masar Worker Token", doc.name, "expires_on", None, update_modified=False
        )
        self.assertIsNone(frappe.db.get_value("Masar Worker Token", doc.name, "expires_on"))
        self.assertEqual(
            masar._resolve_worker(doc._plaintext_token), emp, "a NULL-expiry link must still resolve"
        )

    def test_backfill_stamps_a_future_expiry_and_link_survives(self):
        """The migration's logic: a NULL-expiry live token gets a generous FUTURE
        expiry, and the SAME (pre-existing) link keeps resolving afterwards — proving
        the backfill never instantly invalidates a currently-distributed link."""
        from apex.patches.v1_x.backfill_masar_token_expiry import execute

        emp = self._worker("backfill")
        doc = self._token_doc(emp)
        token = doc._plaintext_token
        frappe.db.set_value(
            "Masar Worker Token", doc.name, "expires_on", None, update_modified=False
        )
        execute()
        stamped = frappe.db.get_value("Masar Worker Token", doc.name, "expires_on")
        self.assertTrue(stamped, "backfill must stamp a NULL-expiry row")
        self.assertGreater(
            frappe.utils.get_datetime(stamped),
            frappe.utils.now_datetime(),
            "the backfilled expiry must be in the future (link not instantly expired)",
        )
        # [#har8a2]
        self.assertEqual(masar._resolve_worker(token), emp)

    # [#bxst8b]

    def test_every_guest_worker_endpoint_carries_a_rate_limit(self):
        """Each ``@frappe.whitelist(allow_guest=True)`` worker endpoint that resolves a
        token must also carry an ``@rate_limit`` — the throttle that stops a personal
        link being driven as a brute-force / enumeration oracle. The decorator wraps the
        function via functools.wraps and stashes ``__wrapped__``; a missing throttle
        leaves that attribute absent."""
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

    # [#l08uie]

    def test_token_field_is_permlevel_one(self):
        """The ``token`` Data field sits at permlevel 1, so a role without a permlevel-1
        read row never receives the secret in a row read — the low roles lose token
        visibility while keeping the rest of the record."""
        meta = frappe.get_meta("Masar Worker Token")
        field = meta.get_field("token")
        self.assertIsNotNone(field, "token field must exist")
        self.assertEqual(field.permlevel, 1, "token must be at permlevel 1 (T-662)")

        # [#eezxp6]
        high = {
            p.role
            for p in meta.permissions
            if getattr(p, "permlevel", 0) == 1 and p.read
        }
        self.assertIn("System Manager", high)
        self.assertIn("Accommodation Manager", high)
        for low in ("Resident Supervisor", "HR User", "Fleet Supervisor"):
            self.assertNotIn(
                low, high, f"{low} must NOT have permlevel-1 read on the token field"
            )


class TestMasarTokenTransport(FrappeTestCase):
    """The httpOnly-cookie transport (T-685/T-705).

    The SPA no longer carries the raw token in the query string or in the page HTML;
    it rides in the httpOnly ``masar_wt`` cookie and the endpoints read it server-side
    via ``_token_from_request``. An explicit arg still wins (backward-compat with a
    freshly distributed ?w= link and unit-test callers)."""

    class _Req:
        def __init__(self, cookies):
            self.cookies = cookies

    def setUp(self):
        frappe.set_user("Administrator")
        self._prev_request = getattr(frappe.local, "request", None)

    def tearDown(self):
        frappe.local.request = self._prev_request
        frappe.set_user("Administrator")

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
        company = (
            frappe.defaults.get_global_default("company")
            or frappe.get_all("Company", limit=1)[0].name
        )
        emp = (
            frappe.get_doc(
                {
                    "doctype": "Employee",
                    "first_name": f"Masar Cookie {self._testMethodName}",
                    "company": company,
                    "status": "Active",
                    "gender": "Male",
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": "2020-01-01",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        token = frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "party_type": "Employee",
                "party": emp,
                "employee": emp,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)._plaintext_token
        frappe.local.request = self._Req({"masar_wt": token})
        # [#jeguz7]
        self.assertEqual(masar._resolve_worker(None), emp)


class TestMasarNotifyHrIqamaExpiring(FrappeTestCase):
    """The one-tap 'notify HR my Iqama is expiring' contract.

    notify_hr_iqama_expiring re-derives days_left from the Employee record (here
    the ``valid_upto`` Iqama-expiry the resolver already falls back to) and raises
    a native HR Notification Log ONLY inside the action window
    (``_IQAMA_NOTIFY_HR_LEAD_DAYS`` == 30). The window gate is server-side, so a
    worker comfortably outside 30 days is a silent no-op even though the same token
    happily resolves — the client can never force HR spam by faking the threshold.
    """

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _company(self):
        return (
            frappe.defaults.get_global_default("company")
            or frappe.get_all("Company", limit=1)[0].name
        )

    def _worker_with_iqama_in(self, suffix, days_from_today):
        """An Active Employee + enabled token whose Iqama (valid_upto) expires
        ``days_from_today`` days out, returning ``(employee, token)``."""
        tag = f"{self._testMethodName}-{suffix}"
        emp = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": f"Masar Iqama {tag}",
                "company": self._company(),
                "status": "Active",
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01",
                "valid_upto": frappe.utils.add_days(frappe.utils.today(), days_from_today),
            }
        ).insert(ignore_permissions=True)
        token = frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "party_type": "Employee",
                "party": emp.name,
                "employee": emp.name,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)._plaintext_token
        return emp.name, token

    def _hr_notifications_for(self, employee):
        """Count HR-targeted Notification Log rows raised for this employee."""
        return frappe.db.count(
            "Notification Log",
            {"document_type": "Employee", "document_name": employee, "type": "Alert"},
        )

    def test_in_window_worker_notifies_hr(self):
        """Iqama 15 days out (<= 30): the endpoint raises a Notification Log to the
        HR inbox, scoped to this worker, and reports notified=True."""
        employee, token = self._worker_with_iqama_in("soon", 15)
        # [#an6uqe]
        self.assertEqual(self._hr_notifications_for(employee), 0)
        # [#t9qxl7]
        self.assertTrue(masar._hr_notify_recipients(), "an HR inbox recipient must exist")

        res = masar.notify_hr_iqama_expiring(token=token)
        self.assertTrue(res["notified"], "an in-window Iqama must notify HR")
        self.assertEqual(res["days_left"], 15)
        self.assertGreaterEqual(res["recipients"], 1)
        # [#d0135r]
        self.assertGreaterEqual(
            self._hr_notifications_for(employee), 1, "an HR Notification Log row must exist"
        )

    def test_out_of_window_worker_is_a_noop(self):
        """Iqama 200 days out (> 30): the same token resolves, but the endpoint
        raises NOTHING and reports notified=False — no HR row is created."""
        employee, token = self._worker_with_iqama_in("later", 200)
        # [#2s7h4d]
        self.assertEqual(masar._resolve_worker(token), employee)

        res = masar.notify_hr_iqama_expiring(token=token)
        self.assertFalse(res["notified"], "an out-of-window Iqama must be a no-op")
        self.assertEqual(res["days_left"], 200)
        self.assertEqual(res["recipients"], 0)
        self.assertEqual(
            self._hr_notifications_for(employee), 0, "no HR row may be created out of window"
        )

    def test_blank_token_is_rejected(self):
        """The write endpoint funnels through _resolve_worker, so a blank token
        fails closed (PermissionError) before any notification is considered."""
        with self.assertRaises(frappe.PermissionError):
            masar.notify_hr_iqama_expiring(token="")

    def test_disabled_hr_recipient_is_skipped(self):
        """C2 (bug fix — behaviour IMPROVED, not merely preserved): the notify loop now
        routes through ``notify_user_system``, which carries an enabled-user check the raw
        ``Notification Log`` insert lacked. BEFORE, a disabled HR user still received a row;
        AFTER, only the enabled recipient does. Two recipients (one enabled, one disabled)
        prove the skip while the enabled path still delivers exactly one scoped alert."""
        employee, token = self._worker_with_iqama_in("mixed", 10)
        suffix = frappe.generate_hash(length=8)
        enabled_user = _user(f"hr_on_{suffix}@example.com", "HR Manager")
        disabled_user = _user(f"hr_off_{suffix}@example.com", "HR Manager")
        frappe.db.set_value("User", disabled_user, "enabled", 0)
        self.addCleanup(frappe.db.set_value, "User", disabled_user, "enabled", 1)

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


class TestMasarEmployeeOnlyDecision(FrappeTestCase):
    """Masar is Employee-only (T-325).

    Every worker surface reads Employee-keyed data; a Temporary Worker has none
    until the daily linking engine matches their passport to a real Employee. The
    decision is enforced at two points and both must stay closed:
      1. minting — the token controller refuses a Temporary-Worker party, so a
         supervisor can never hand out a dead link; and
      2. resolving — should a temp token exist anyway (e.g. a legacy/manual row),
         ``_resolve_worker`` rejects it with a DISTINCT, honest message rather
         than the misleading "invalid or has been disabled", while still failing
         closed (PermissionError — it resolves to no one).
    """

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _make_temporary_worker(self, suffix):
        """An Active Temporary Worker (passport-only, no Employee yet)."""
        tag = f"{self._testMethodName}-{suffix}"
        return frappe.get_doc(
            {
                "doctype": "Temporary Worker",
                "worker_name": f"Temp Worker {tag}",
                "passport_number": f"T325-{frappe.generate_hash(length=10)}",
                "arrival_date": frappe.utils.today(),
                "status": "Active",
            }
        ).insert(ignore_permissions=True)

    def test_controller_refuses_to_mint_a_temporary_worker_token(self):
        """The token controller rejects a Temporary-Worker party at save, so no
        dead Masar link can ever be issued for a worker with no Employee."""
        tw = self._make_temporary_worker("mint")
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(
                {
                    "doctype": "Masar Worker Token",
                    "party_type": "Temporary Worker",
                    "party": tw.name,
                    "enabled": 1,
                }
            ).insert(ignore_permissions=True)
        # [#eug3ep]
        self.assertFalse(
            frappe.db.exists("Masar Worker Token", {"party_type": "Temporary Worker", "party": tw.name}),
            "no Temporary-Worker token row may be created",
        )

    def test_temporary_worker_token_resolves_with_a_distinct_message(self):
        """A Temporary-Worker token (forced in below the controller, as a legacy
        row would be) fails closed with the DISTINCT not-linked-yet message — not
        the generic invalid/disabled one — and resolves to no employee."""
        tw = self._make_temporary_worker("resolve")
        forced_token = frappe.generate_hash(length=48)
        # [#4ziom4]
        doc = frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "name": tw.name,
                "party_type": "Temporary Worker",
                "party": tw.name,
                "employee": None,
                "enabled": 1,
                "token": _hash_token(forced_token),
            }
        )
        doc.db_insert()
        # [#bqonxo]
        row = frappe.db.get_value(
            "Masar Worker Token",
            {"token": _hash_token(forced_token)},
            ["party_type", "employee", "enabled"],
            as_dict=True,
        )
        self.assertEqual(row.party_type, "Temporary Worker")
        self.assertFalse(row.employee, "a temp-worker token carries no employee")
        self.assertEqual(row.enabled, 1)

        with self.assertRaises(frappe.PermissionError) as ctx:
            masar._resolve_worker(forced_token)
        # [#9uulji]
        self.assertIn("not linked to a permanent Employee", str(ctx.exception))
        self.assertNotIn("invalid or has been disabled", str(ctx.exception))

        # [#gbwobw]
        with self.assertRaises(frappe.PermissionError):
            masar.get_worker_context(token=forced_token)


class TestMasarWorkerTokenAutoname(FrappeTestCase):
    """A token created with ONLY the Employee link must name + validate.

    autoname is ``field:party``, which set_new_name resolves BEFORE before_validate
    runs. If party were derived only in before_validate, a token minted with just the
    Employee link would fail naming with "Worker is required" before it ever reached
    validation. before_insert mirrors employee -> party so naming has it; this is the
    guard for that root-cause fix (the get_or_create_for_employee path passes no party).
    """

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _company(self):
        return (
            frappe.defaults.get_global_default("company")
            or frappe.get_all("Company", limit=1)[0].name
        )

    def _make_employee(self, suffix):
        tag = f"{self._testMethodName}-{suffix}"
        return (
            frappe.get_doc(
                {
                    "doctype": "Employee",
                    "first_name": f"Masar Autoname {tag}",
                    "company": self._company(),
                    "status": "Active",
                    "gender": "Male",
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": "2020-01-01",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def test_token_with_only_employee_names_and_validates(self):
        """Insert a token supplying ONLY employee (no party / party_type). It must
        insert, autoname to the employee (field:party, party derived from employee),
        and back-fill party_type/party — exactly the case that previously threw."""
        emp = self._make_employee("only-emp")
        doc = frappe.get_doc(
            {"doctype": "Masar Worker Token", "employee": emp}
        ).insert(ignore_permissions=True)
        # [#hr7zks]
        self.assertEqual(doc.name, emp, "token must autoname to the employee via field:party")
        self.assertEqual(doc.party, emp)
        self.assertEqual(doc.party_type, "Employee")
        self.assertEqual(doc.employee, emp)
        self.assertTrue(doc.token, "a token must be minted on insert")

    def test_get_or_create_for_brand_new_employee_succeeds(self):
        """get_or_create_for_employee inserts {doctype, employee} with no party; it
        must succeed for a brand-new Employee and return the named token row."""
        emp = self._make_employee("goc")
        # [#tetcl6]
        self.assertFalse(frappe.db.exists("Masar Worker Token", {"employee": emp}))
        doc = get_or_create_for_employee(emp)
        self.assertEqual(doc.employee, emp)
        self.assertEqual(doc.name, emp)
        self.assertEqual(doc.party, emp)
        self.assertTrue(frappe.db.exists("Masar Worker Token", {"employee": emp}))
        # [#4guxi0]
        again = get_or_create_for_employee(emp)
        self.assertEqual(again.name, doc.name)
