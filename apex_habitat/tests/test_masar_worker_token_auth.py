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

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.apex_core.doctype.masar_worker_token.masar_worker_token import (
    get_or_create_for_employee,
)
from apex_habitat.salis.api import masar

# Employee.status values the resolver fails closed on, verbatim from
# _resolve_worker ("Inactive", "Left"); "Active" is the standard happy-path value
# proven insertable by tests/factories.make_employee.
BLOCKED_STATUSES = ("Inactive", "Left")


class TestMasarWorkerTokenAuth(FrappeTestCase):
    def setUp(self):
        # Build fixtures as Administrator; restore in tearDown so a changed user
        # never leaks into another test.
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    # fixtures

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
        """Issue a Masar Worker Token for ``employee`` and return its minted token
        string. The token value is server-generated (read-only, auto in
        before_insert), so we read it back rather than supplying it."""
        doc = frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                # autoname is field:party, so party must be set before insert; the
                # token's party IS the Employee (party_type Employee).
                "party_type": "Employee",
                "party": employee,
                "employee": employee,
                "enabled": enabled,
            }
        ).insert(ignore_permissions=True)
        self.assertTrue(doc.token, "fixture sanity: a token must be minted on insert")
        self.assertEqual(doc.employee, employee, "fixture sanity: token bound to the employee")
        return doc.token

    # the contract

    def test_token_resolves_to_only_its_own_employee(self):
        """Two seeded workers, two tokens: token A resolves to A and ONLY A —
        never B. This is the anti-leak invariant; if it widened, one worker's link
        would surface another worker's data."""
        emp_a = self._make_employee("a")
        emp_b = self._make_employee("b")
        token_a = self._make_token(emp_a)
        token_b = self._make_token(emp_b)

        # Non-vacuous: the seed produced two distinct workers + two distinct tokens.
        self.assertNotEqual(emp_a, emp_b)
        self.assertNotEqual(token_a, token_b)

        # The resolver itself (the SOLE authorization chokepoint) is exactly scoped.
        self.assertEqual(masar._resolve_worker(token_a), emp_a)
        self.assertNotEqual(masar._resolve_worker(token_a), emp_b)
        self.assertEqual(masar._resolve_worker(token_b), emp_b)

        # And the public guest endpoint returns ONLY employee A for token A.
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
        # Non-vacuous: confirm this token genuinely matches no row before asserting.
        self.assertFalse(frappe.db.exists("Masar Worker Token", {"token": bogus}))
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(bogus)
        with self.assertRaises(frappe.PermissionError):
            masar.get_worker_context(token=bogus)

    def test_disabled_token_is_rejected(self):
        """enabled=0 revokes the link: a token whose row exists but is disabled must
        403, even though its Employee is a real, Active worker."""
        emp = self._make_employee("disabled")
        token = self._make_token(emp, enabled=0)
        # Non-vacuous: the row exists and is bound to the worker — it is the
        # enabled flag alone that must close the door.
        self.assertEqual(
            frappe.db.get_value("Masar Worker Token", {"token": token}, "enabled"),
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
            # Non-vacuous: the worker really now carries the blocked status.
            self.assertEqual(
                frappe.db.get_value("Employee", emp, "status"),
                status,
                f"fixture sanity: employee status must be {status}",
            )
            with self.assertRaises(frappe.PermissionError):
                masar._resolve_worker(token)
            with self.assertRaises(frappe.PermissionError):
                masar.get_worker_context(token=token)


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
        ).insert(ignore_permissions=True).token
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
        # Non-vacuous: no HR notification exists for this fresh worker yet.
        self.assertEqual(self._hr_notifications_for(employee), 0)
        # Non-vacuous: HR Manager (fallback System Manager) has at least one user,
        # else the notification has no destination and the test proves nothing.
        self.assertTrue(masar._hr_notify_recipients(), "an HR inbox recipient must exist")

        res = masar.notify_hr_iqama_expiring(token=token)
        self.assertTrue(res["notified"], "an in-window Iqama must notify HR")
        self.assertEqual(res["days_left"], 15)
        self.assertGreaterEqual(res["recipients"], 1)
        # The native HR notification row was actually created for THIS worker.
        self.assertGreaterEqual(
            self._hr_notifications_for(employee), 1, "an HR Notification Log row must exist"
        )

    def test_out_of_window_worker_is_a_noop(self):
        """Iqama 200 days out (> 30): the same token resolves, but the endpoint
        raises NOTHING and reports notified=False — no HR row is created."""
        employee, token = self._worker_with_iqama_in("later", 200)
        # The token is genuinely valid (resolves to this worker) — only the window
        # closes the action, not a bad token.
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
        # Non-vacuous: the guard, not a missing party, blocked it — no row landed.
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
        # db_insert bypasses the controller guard + autoname, mirroring a row that
        # predates the Employee-only enforcement; party_type is the temp worker and
        # employee is empty exactly as sync_party_employee leaves it.
        doc = frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "name": tw.name,
                "party_type": "Temporary Worker",
                "party": tw.name,
                "employee": None,
                "enabled": 1,
                "token": forced_token,
            }
        )
        doc.db_insert()
        # Non-vacuous: the row genuinely exists, is enabled, and has no employee.
        row = frappe.db.get_value(
            "Masar Worker Token",
            {"token": forced_token},
            ["party_type", "employee", "enabled"],
            as_dict=True,
        )
        self.assertEqual(row.party_type, "Temporary Worker")
        self.assertFalse(row.employee, "a temp-worker token carries no employee")
        self.assertEqual(row.enabled, 1)

        with self.assertRaises(frappe.PermissionError) as ctx:
            masar._resolve_worker(forced_token)
        # The message is the honest temp-worker one, distinct from invalid/disabled.
        self.assertIn("not linked to a permanent Employee", str(ctx.exception))
        self.assertNotIn("invalid or has been disabled", str(ctx.exception))

        # And the public guest endpoint fails closed the same way (no data leak).
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
        # Named off party (== employee) and the mirror fields were back-filled.
        self.assertEqual(doc.name, emp, "token must autoname to the employee via field:party")
        self.assertEqual(doc.party, emp)
        self.assertEqual(doc.party_type, "Employee")
        self.assertEqual(doc.employee, emp)
        self.assertTrue(doc.token, "a token must be minted on insert")

    def test_get_or_create_for_brand_new_employee_succeeds(self):
        """get_or_create_for_employee inserts {doctype, employee} with no party; it
        must succeed for a brand-new Employee and return the named token row."""
        emp = self._make_employee("goc")
        # Non-vacuous: no token row exists for this fresh worker yet.
        self.assertFalse(frappe.db.exists("Masar Worker Token", {"employee": emp}))
        doc = get_or_create_for_employee(emp)
        self.assertEqual(doc.employee, emp)
        self.assertEqual(doc.name, emp)
        self.assertEqual(doc.party, emp)
        self.assertTrue(frappe.db.exists("Masar Worker Token", {"employee": emp}))
        # Idempotent: a second call returns the same row, not a duplicate.
        again = get_or_create_for_employee(emp)
        self.assertEqual(again.name, doc.name)
