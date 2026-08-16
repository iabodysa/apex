# Copyright (c) 2026, AFMCO and contributors
"""Adversarial coverage for worker and driver portal bearer isolation.

This file's name carries the module's retired name; the module it guards lives at
``apex_core/utils/portal_identity.py`` (its public surface -- ``resolve_portal_subject``,
``validate_subject_binding``, ``as_capacity``, ``revoke_subject_tokens``,
``log_credential_event``, ``hash_token``, ``portal_room``, ``WORKER``, ``DRIVER``,
``CAPACITY_USERS`` -- is unchanged), imported below as ``token_security`` so the body
of this file reads the same regardless of the module's own name.

SIZE, DELIBERATE: this file exceeds the 2x rule and stays. Its
subject is not one module but one SECURITY SURFACE — the unauthenticated bearer path
through ``apex_core/utils/portal_identity.py`` (554 lines) *and*
``apex_core/doctype/masar_worker_token/masar_worker_token.py`` (673 lines), 1,227 lines
of subject in total. Against that the file is ~1.2x, not 3x; the old header measured it
against one of the two modules. What it holds is not repetition: two audiences that must
never resolve each other's credential, six issuance entry points that each call
``authorize_issuance`` independently, five revocation hooks, a per-IP throttle, a
row-lock race proved over two connections, and role/scope authorization positive and
negative in both audiences. A case removed here removes an entry point nobody else
guards, so the ratio is bought, not inherited.
"""

import base64
from contextlib import contextmanager
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase, timeout
from frappe.utils.password import encrypt
from PIL import Image

import apex
from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    _hash_token,
    batch_issue_driver_links,
    batch_issue_worker_links,
    get_or_create_for_driver,
    get_or_create_for_employee,
    issue_driver_link,
    issue_worker_link,
    resolve_driver_token,
)
from apex.apex_core.utils import portal_identity as token_security
from apex.salis.api import boarding, masar
from apex.salis.api.driver_portal import profile, trips
from apex.www import driver as driver_page, masar as masar_page


# Rooted on the INSTALLED package, never on this file: `Path(__file__).parents[1]` names
# `.claude/tests/apex/apex_core`, a directory that has never held a `doctype/` tree, so
# anchoring there makes every case in this file error in setUp with FileNotFoundError on
# the token metadata.
APP_ROOT = Path(apex.__file__).resolve().parent
TOKEN_METADATA = (
    APP_ROOT / "apex_core" / "doctype" / "masar_worker_token" / "masar_worker_token.json"
)


def _image_data_uri(image_format="PNG"):
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color=(12, 34, 56)).save(
        buffer,
        format=image_format,
    )
    mime = {"JPEG": "jpeg", "PNG": "png", "WEBP": "webp"}[image_format]
    return "data:image/" + mime + ";base64," + base64.b64encode(buffer.getvalue()).decode()


# `_image_bytes`, `_compact_png_with_dimensions`, `DRIVER_IMAGE_HELPER` and the
# ast/inspect/zlib/urllib imports are not defined here: nothing in this file's AST
# references them, so they are dead weight this module does not carry.

BAD_TOKEN_SUBNET = "2001:db8:5ec0::"


def _fresh_ip():
    """An address no other block in the app can be using: this file's own slice of
    the RFC 3849 documentation prefix, plus a random suffix.

    The portal bad-token window is keyed on the ADDRESS ALONE, so sharing a subnet
    with another test file would let this file's failed tokens spend that file's
    budget. TestThrottleAddressIsolation (apex_core/utils/test_portal_token_throttle.py)
    holds every such file's subnet apart app-wide.
    """
    return BAD_TOKEN_SUBNET + frappe.generate_hash(length=12)


class _Request:
    # No default address: the address decides WHICH window a call spends, so a
    # caller that forgets one must fail loudly rather than land on a shared window.
    def __init__(self, cookies, remote_addr):
        self.cookies = cookies
        self.remote_addr = remote_addr
        self.host = None


@contextmanager
def _request_cookies(cookies, ip=None):
    """One request surface per block, on its OWN address unless the caller pins one.
    Yields the address so a throttle test can address its window."""
    ip = ip or _fresh_ip()
    sentinel = object()
    previous_request = getattr(frappe.local, "request", sentinel)
    previous_ip = getattr(frappe.local, "request_ip", sentinel)
    previous_form = getattr(frappe.local, "form_dict", sentinel)
    frappe.local.request = _Request(cookies, ip)
    frappe.local.request_ip = ip
    frappe.local.form_dict = frappe._dict(
        {"cmd": "portal-security-" + frappe.generate_hash(length=12)}
    )
    try:
        yield ip
    finally:
        for fieldname, previous in (
            ("request", previous_request),
            ("request_ip", previous_ip),
            ("form_dict", previous_form),
        ):
            if previous is sentinel:
                if hasattr(frappe.local, fieldname):
                    delattr(frappe.local, fieldname)
            else:
                setattr(frappe.local, fieldname, previous)


@contextmanager
def _request_from_ip(ip, cmd, cookies=None):
    """The same request surface as ``_request_cookies``, with the remote address and
    the ``cmd`` both pinned by the caller.

    The bad-token window ignores ``cmd`` by design (it is keyed on the address
    alone), so pinning it here is what proves the endpoint no longer changes the
    answer while the two addresses are compared.
    """
    sentinel = object()
    previous = {
        name: getattr(frappe.local, name, sentinel)
        for name in ("request", "request_ip", "form_dict")
    }
    frappe.local.request = _Request(cookies or {}, ip)
    frappe.local.request_ip = ip
    frappe.local.form_dict = frappe._dict({"cmd": cmd})
    try:
        yield
    finally:
        for fieldname, value in previous.items():
            if value is sentinel:
                if hasattr(frappe.local, fieldname):
                    delattr(frappe.local, fieldname)
            else:
                setattr(frappe.local, fieldname, value)


class _as_user:
    def __init__(self, user):
        self.user = user

    def __enter__(self):
        self.previous = frappe.session.user
        frappe.set_user(self.user)
        token_meta = frappe.get_meta("Masar Worker Token")
        self.previous_autoname = token_meta.autoname
        self.previous_permissions = token_meta.permissions
        doctype_path = TOKEN_METADATA
        metadata = json.loads(doctype_path.read_text(encoding="utf-8"))
        token_meta.permissions = [
            frappe._dict(row) for row in metadata["permissions"]
        ]
        token_meta.autoname = "hash"
        return self

    def __exit__(self, *exc):
        token_meta = frappe.get_meta("Masar Worker Token")
        token_meta.autoname = self.previous_autoname
        token_meta.permissions = self.previous_permissions
        frappe.set_user(self.previous)
        return False


class TestPortalTokenSecurity(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        self.employee = self._make_employee()
        self.driver = self._make_driver()
        token_meta = frappe.get_meta("Masar Worker Token")
        self._original_autoname = token_meta.autoname
        self._original_permissions = token_meta.permissions
        doctype_path = TOKEN_METADATA
        metadata = json.loads(doctype_path.read_text(encoding="utf-8"))
        token_meta.autoname = "hash"
        token_meta.permissions = [
            frappe._dict(row) for row in metadata["permissions"]
        ]

    def tearDown(self):
        token_meta = frappe.get_meta("Masar Worker Token")
        token_meta.autoname = self._original_autoname
        token_meta.permissions = self._original_permissions
        frappe.set_user("Administrator")

    def _company(self):
        return (
            frappe.defaults.get_global_default("company")
            or frappe.get_all("Company", limit=1)[0].name
        )

    def _make_employee(self, phone=None):
        tag = frappe.generate_hash(length=12).lower()
        return (
            frappe.get_doc(
                {
                    "doctype": "Employee",
                    "first_name": f"Portal Security {tag}",
                    "company": self._company(),
                    "status": "Active",
                    "gender": "Male",
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": "2020-01-01",
                    "cell_number": phone,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _make_driver(self, project=None, phone=None, employee=None):
        tag = frappe.generate_hash(length=12).lower()
        return (
            frappe.get_doc(
                {
                    "doctype": "Salis Driver",
                    "full_name": f"Portal Security Driver {tag}",
                    "status": "Active",
                    "project": project,
                    "phone": phone,
                    "employee": employee,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _make_building(self):
        tag = frappe.generate_hash(length=12).upper()
        return (
            frappe.get_doc(
                {"doctype": "Building", "building_name": f"TOKEN-{tag}"}
            )
            .insert(
                ignore_permissions=True,
                ignore_links=True,
                ignore_mandatory=True,
            )
            .name
        )

    def _make_project(self):
        tag = frappe.generate_hash(length=12).upper()
        return (
            frappe.get_doc(
                {"doctype": "Project", "project_name": f"TOKEN-{tag}"}
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _make_user(self, role, *, allow=None, for_value=None):
        """A throwaway user holding one role, DELETED when the test that asked for it ends.

        The email carries a fresh hash, so every run of this class used to leave a new
        `portal-security-*` account behind holding a real role. Those accounts join every
        role-based recipient list for ever, and four unrelated notification tests assert their
        own user is in such a list — so they began failing against a list of thirty-seven
        strangers none of them created. A fixture that outlives its test is not a fixture.
        """
        tag = frappe.generate_hash(length=12).lower()
        user = (
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": f"portal-security-{tag}@example.com",
                    "first_name": "Portal Security",
                    "send_welcome_email": 0,
                    "roles": [{"role": role}],
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        self.addCleanup(frappe.delete_doc, "User", user, force=True, ignore_permissions=True)
        if allow and for_value:
            permission = frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "user": user,
                    "allow": allow,
                    "for_value": for_value,
                }
            ).insert(ignore_permissions=True)
            self.addCleanup(
                frappe.delete_doc,
                "User Permission",
                permission.name,
                force=True,
                ignore_permissions=True,
            )
        return user

    def _house(self, employee, building):
        assignment = frappe.get_doc(
            {
                "doctype": "Housing Assignment",
                "party_type": "Employee",
                "party": employee,
                "employee": employee,
                "building": building,
                "check_in_date": frappe.utils.today(),
            }
        )
        assignment.flags.ignore_validate = True
        assignment.insert(
            ignore_permissions=True,
            ignore_links=True,
            ignore_mandatory=True,
        )
        frappe.db.set_value(
            "Housing Assignment", assignment.name, "docstatus", 1
        )
        return assignment.name

    def _worker_token(self):
        return frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "holder_type": "Worker",
                "party_type": "Employee",
                "party": self.employee,
                "employee": self.employee,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)

    def _driver_token(self, driver=None):
        return frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "holder_type": "Driver",
                "driver": driver or self.driver,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)

    def _cleared_clearance(self, driver):
        doc = frappe.get_doc(
            {
                "doctype": "Driver Clearance",
                "driver": driver,
                "status": "Open",
                "clearance_reason": "End of Assignment",
                "vehicle_returned": 1,
                "fuel_chip_returned": 1,
                "custody_returned": 1,
            }
        ).insert(ignore_permissions=True)
        frappe.db.set_value(
            "Driver Clearance",
            doc.name,
            {"status": "Cleared", "docstatus": 1},
            update_modified=False,
        )
        return frappe.get_doc("Driver Clearance", doc.name)

    def _configure_push(self):
        frappe.db.set_single_value(
            "Salis Settings",
            {
                "enable_web_push": 1,
                "web_push_vapid_public_key": "BNportal_security_public_key_000000000000000000000000000000000000000000",
                "web_push_vapid_private_key": "portal-security-private-key",
                "web_push_vapid_subject": "mailto:portal-security@example.com",
            },
        )

    def _assert_driver_read_rejected_before_trip_query(self, cookies):
        frappe.set_user("Guest")
        real_get_all = trips.frappe.get_all
        with _request_cookies(cookies), patch.object(
            trips.frappe, "get_all", wraps=real_get_all
        ) as reads:
            with self.assertRaises(frappe.PermissionError):
                trips.my_trips_today()
        trip_reads = [call for call in reads.call_args_list if call.args[0] == "Dispatch Trip"]
        self.assertEqual(trip_reads, [])

    # These five look like one parameterised case and are NOT. They must stay
    # five test METHODS. `_driver_token()` mints a Salis Driver off a naming series, and
    # only FrappeTestCase's per-TEST rollback returns the counter; driving them as
    # subTests inside one method reds with
    # `IntegrityError (1062) Duplicate entry 'DRV-...' for key 'PRIMARY'` on the second
    # arm. `_assert_driver_read_rejected_before_trip_query` also leaves the session on
    # Guest, which the next arm's issuance is not authorised for. Measured, not assumed.
    def test_missing_driver_credential_fails_before_sensitive_read(self):
        self._assert_driver_read_rejected_before_trip_query({})

    def test_worker_credential_fails_before_sensitive_driver_read(self):
        worker = self._worker_token()
        self._assert_driver_read_rejected_before_trip_query(
            {"masar_wt": worker._plaintext_token}
        )

    def test_disabled_driver_credential_fails_before_sensitive_read(self):
        token = self._driver_token()
        frappe.db.set_value("Masar Worker Token", token.name, "enabled", 0)
        self._assert_driver_read_rejected_before_trip_query(
            {"masar_dt": token._plaintext_token}
        )

    def test_expired_driver_credential_fails_before_sensitive_read(self):
        token = self._driver_token()
        frappe.db.set_value(
            "Masar Worker Token",
            token.name,
            "expires_on",
            frappe.utils.add_days(frappe.utils.now_datetime(), -1),
        )
        self._assert_driver_read_rejected_before_trip_query(
            {"masar_dt": token._plaintext_token}
        )

    def test_inactive_driver_credential_fails_before_sensitive_read(self):
        token = self._driver_token()
        frappe.db.set_value("Salis Driver", self.driver, "status", "Stopped")
        try:
            self._assert_driver_read_rejected_before_trip_query(
                {"masar_dt": token._plaintext_token}
            )
        finally:
            frappe.db.set_value("Salis Driver", self.driver, "status", "Active")

    def test_valid_guest_driver_credential_reads_only_its_profile(self):
        token = self._driver_token()
        frappe.set_user("Guest")
        with _request_cookies({"masar_dt": token._plaintext_token}):
            result = profile.get_driver_profile()
        self.assertEqual(result["name"], self.driver)

















    def test_worker_photo_door_refuses_a_renamed_non_image(self):
        """Both Masar photo doors decide on the bytes, not the extension: judging by
        EXTENSION alone would RENAME a filename outside the allowed list to .jpg rather
        than refuse it, storing a text file under an image name (measured: a 39-byte text
        file lands as .png, .gif, .heic and .webp)."""
        text = base64.b64encode(b"this is not an image, it is a text file").decode()
        fake_jpeg = "data:image/jpeg;base64," + text
        doc = frappe._dict(doctype="Resident Request", name="REQ-1")
        with patch("frappe.utils.file_manager.save_file") as save:
            for filename in ("not-an-image.txt", "notes.png", "notes.gif",
                             "notes.heic", "notes.webp", "photo.jpg"):
                with self.subTest(filename=filename), self.assertRaises(
                    frappe.ValidationError
                ):
                    masar._attach_worker_photo(doc, fake_jpeg, filename)
            # A container the verifier cannot open is refused, never renamed.
            with self.assertRaises(frappe.ValidationError):
                masar._attach_worker_photo(doc, text, "bare-base64.png")
        save.assert_not_called()

    def test_worker_photo_extension_comes_from_the_verified_bytes(self):
        """A real PNG offered under a .jpeg name is stored as .png: the extension is
        derived from what the bytes proved, so nothing can be laundered into a name."""
        saved = frappe._dict(file_url="/private/files/evidence.png")
        doc = MagicMock(name="resident_request")
        doc.doctype = "Resident Request"
        doc.name = "REQ-1"
        with patch("frappe.utils.file_manager.save_file", return_value=saved) as save:
            masar._attach_worker_photo(doc, _image_data_uri("PNG"), "camera roll/IMG_1.jpeg")
        self.assertEqual(save.call_args.args[0], "IMG_1.png")
        self.assertEqual(save.call_args.kwargs["is_private"], 1)
        doc.db_set.assert_called_once_with("attachment", saved.file_url)






    def test_boarding_scan_rate_is_exactly_sixty_per_minute(self):
        self.assertEqual(boarding.SCAN_ACTOR_LIMIT, 60)
        self.assertEqual(boarding.SCAN_UNRESOLVED_IP_LIMIT, 60)





    def test_worker_resolver_rejects_driver_audience(self):
        token = self._driver_token()
        frappe.db.set_value(
            "Masar Worker Token",
            token.name,
            {
                "party_type": "Employee",
                "party": self.employee,
                "employee": self.employee,
            },
            update_modified=False,
        )

        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(token._plaintext_token)

    def test_driver_resolver_rejects_worker_audience(self):
        token = self._worker_token()
        frappe.db.set_value(
            "Masar Worker Token",
            token.name,
            "driver",
            self.driver,
            update_modified=False,
        )

        with self.assertRaises(frappe.PermissionError):
            resolve_driver_token(token._plaintext_token)

    def test_driver_holder_type_rejects_worker_fields_on_insert_full_or_partial(self):
        """holder_type=Driver refuses ANY worker-audience field on insert, whether
        the worker subject is fully populated or only party_type is present."""
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(
                {
                    "doctype": "Masar Worker Token",
                    "holder_type": "Driver",
                    "driver": self.driver,
                    "party_type": "Employee",
                    "party": self.employee,
                    "employee": self.employee,
                }
            ).insert(ignore_permissions=True)

        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(
                {
                    "doctype": "Masar Worker Token",
                    "holder_type": "Driver",
                    "driver": self.driver,
                    "party_type": "Employee",
                }
            ).insert(ignore_permissions=True)


    def test_mixed_worker_binding_rejected_on_save(self):
        token = self._worker_token()
        token.driver = self.driver

        with self.assertRaises(frappe.ValidationError):
            token.save(ignore_permissions=True)

    def test_resident_supervisor_cannot_retarget_driver_token_to_worker(self):
        building = self._make_building()
        employee = self._make_employee()
        self._house(employee, building)
        resident = self._make_user(
            "Resident Supervisor", allow="Building", for_value=building
        )
        token = self._driver_token()
        original_binding = frappe.db.get_value(
            "Masar Worker Token",
            token.name,
            ["holder_type", "party_type", "party", "employee", "driver"],
            as_dict=True,
        )

        with _as_user(resident):
            doc = frappe.get_doc("Masar Worker Token", token.name)
            doc.holder_type = "Worker"
            doc.party_type = "Employee"
            doc.party = employee
            doc.employee = employee
            doc.driver = None
            with self.assertRaises(frappe.ValidationError):
                doc.save()

        persisted = frappe.db.get_value(
            "Masar Worker Token",
            token.name,
            ["holder_type", "party_type", "party", "employee", "driver"],
            as_dict=True,
        )
        self.assertEqual(dict(persisted), dict(original_binding))

    def test_resident_supervisor_cannot_retarget_worker_token(self):
        building = self._make_building()
        other_employee = self._make_employee()
        self._house(self.employee, building)
        self._house(other_employee, building)
        resident = self._make_user(
            "Resident Supervisor", allow="Building", for_value=building
        )
        token = self._worker_token()
        original_binding = frappe.db.get_value(
            "Masar Worker Token",
            token.name,
            ["holder_type", "party_type", "party", "employee", "driver"],
            as_dict=True,
        )

        with _as_user(resident):
            doc = frappe.get_doc("Masar Worker Token", token.name)
            doc.party = other_employee
            doc.employee = other_employee
            with self.assertRaises(frappe.ValidationError):
                doc.save()

        persisted = frappe.db.get_value(
            "Masar Worker Token",
            token.name,
            ["holder_type", "party_type", "party", "employee", "driver"],
            as_dict=True,
        )
        self.assertEqual(dict(persisted), dict(original_binding))

    def test_party_type_is_conditionally_required_only_for_workers(self):
        doctype_path = TOKEN_METADATA
        metadata = json.loads(doctype_path.read_text(encoding="utf-8"))
        party_type = next(
            field for field in metadata["fields"] if field["fieldname"] == "party_type"
        )

        self.assertFalse(party_type.get("reqd"))
        self.assertNotIn("default", party_type)
        self.assertEqual(
            party_type["mandatory_depends_on"],
            "eval:doc.holder_type!='Driver'",
        )

    def test_null_expiry_rejected_for_both_audiences(self):
        worker_token = self._worker_token()
        driver_token = self._driver_token()
        frappe.db.set_value(
            "Masar Worker Token",
            worker_token.name,
            "expires_on",
            None,
            update_modified=False,
        )
        frappe.db.set_value(
            "Masar Worker Token",
            driver_token.name,
            "expires_on",
            None,
            update_modified=False,
        )

        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(worker_token._plaintext_token)
        with self.assertRaises(frappe.PermissionError):
            resolve_driver_token(driver_token._plaintext_token)

    def test_only_active_subjects_resolve(self):
        worker_token = self._worker_token()
        driver_token = self._driver_token()

        for status in ("Inactive", "Suspended", "Left"):
            with self.subTest(audience="Worker", status=status):
                frappe.db.set_value("Employee", self.employee, "status", status)
                with self.assertRaises(frappe.PermissionError):
                    masar._resolve_worker(worker_token._plaintext_token)
        frappe.db.set_value("Employee", self.employee, "status", "Active")

        for status in ("Stopped", "On Leave", "Released"):
            with self.subTest(audience="Driver", status=status):
                frappe.db.set_value("Salis Driver", self.driver, "status", status)
                with self.assertRaises(frappe.PermissionError):
                    resolve_driver_token(driver_token._plaintext_token)

    def _window_name(self, ip):
        """The RAW cache name of one address's bad-token window."""
        return token_security.BAD_TOKEN_WINDOW_KEY.format(ip)

    def _assert_window_cleared(self, name):
        """Registered BEFORE the delete so addCleanup's LIFO order runs it AFTER:
        this is what proves the delete actually landed rather than silently missing
        (a pre-made key handed to ``delete_value`` is prefixed a
        second time, redis_wrapper.py:141-142, and the counter outlives the test)."""
        self.assertIsNone(
            frappe.cache.get(frappe.cache.make_key(name)),
            f"the bad-token window {name} outlived its cleanup",
        )

    def _clean_window(self, ip):
        """Clear this address's window now and again at teardown, PROVING both."""
        name = self._window_name(ip)
        self.addCleanup(self._assert_window_cleared, name)
        self.addCleanup(frappe.cache.delete_value, name)
        frappe.cache.delete_value(name)
        self._assert_window_cleared(name)
        return name

    def test_bad_token_attempts_from_one_ip_are_rate_limited(self):
        """Defense-in-depth: the (N+1)th rapid failed token from one IP is rejected
        with RateLimitExceededError (HTTP 429), while the first N fail closed with the
        ordinary PermissionError. Bench-run integration test -- the throttle counts in
        Redis and is a no-op without a request context, so it needs the live
        request/cache a bench provides."""
        limit = token_security.BAD_TOKEN_ATTEMPTS_PER_MINUTE
        bogus = "definitely-not-a-real-token"
        frappe.set_user("Guest")
        with _request_cookies({}) as ip:
            self._clean_window(ip)
            for _ in range(limit):
                with self.assertRaises(frappe.PermissionError):
                    resolve_driver_token(bogus)
            with self.assertRaises(frappe.RateLimitExceededError) as raised:
                resolve_driver_token(bogus)
        self.assertEqual(getattr(raised.exception, "http_status_code", None), 429)

    def test_valid_token_is_never_charged_against_the_bad_token_throttle(self):
        """A legitimate holder is never blocked: a VALID credential resolved far past
        the per-IP failure ceiling still returns its subject every time, and the
        address's window is still EMPTY afterwards -- only FAILED resolutions are
        charged, so a valid link never consumes the budget."""
        token = self._driver_token()
        limit = token_security.BAD_TOKEN_ATTEMPTS_PER_MINUTE
        frappe.set_user("Guest")
        with _request_cookies({}) as ip:
            name = self._clean_window(ip)
            for _ in range(limit * 2 + 1):
                self.assertEqual(
                    resolve_driver_token(token._plaintext_token), self.driver
                )
            self.assertIsNone(frappe.cache.get(frappe.cache.make_key(name)))

    def test_www_entry_points_throttle_repeated_bad_links_from_one_ip(self):
        """Both www entries enforce the per-IP throttle: a flood of well-formed but
        unknown links (/masar?w=, /driver?d=) from one IP is cut off with 429, while
        each well-formed link still redirects to the clean URL so the secret leaves the
        address bar. Bench-run integration test (live Redis request context)."""
        limit = token_security.BAD_TOKEN_ATTEMPTS_PER_MINUTE
        bogus = "abcdef0123456789abcdef0123456789"
        for page, field in ((masar_page, "w"), (driver_page, "d")):
            with self.subTest(entry=page.__name__):
                frappe.set_user("Guest")
                with _request_cookies({}) as ip:
                    self._clean_window(ip)
                    frappe.local.form_dict[field] = bogus
                    for _ in range(limit):
                        with self.assertRaises(frappe.Redirect):
                            page.get_context(frappe._dict())
                    with self.assertRaises(frappe.RateLimitExceededError) as raised:
                        page.get_context(frappe._dict())
                self.assertEqual(
                    getattr(raised.exception, "http_status_code", None), 429
                )

    def test_bad_token_budget_is_one_shared_window_across_endpoints(self):
        """The advertised 10/60s is per IP FULL STOP, not 10 per IP per endpoint.

        frappe's own @rate_limit welds ``form_dict.cmd`` into its key
        (rate_limiter.py:155), which hands each of the guest endpoints a private N and
        multiplies the real ceiling by however many are reachable. Failures split
        across two DIFFERENT cmd values must therefore trip the SAME ceiling, and a
        third endpoint must find the budget already spent.
        """
        limit = token_security.BAD_TOKEN_ATTEMPTS_PER_MINUTE
        bogus = "definitely-not-a-real-token"
        ip = _fresh_ip()
        name = self._clean_window(ip)
        half = limit // 2

        frappe.set_user("Guest")
        for cmd, attempts in (
            ("a210.endpoint.one", half),
            ("a210.endpoint.two", limit - half),
        ):
            with _request_from_ip(ip, cmd):
                for _ in range(attempts):
                    with self.assertRaises(frappe.PermissionError):
                        resolve_driver_token(bogus)
        with _request_from_ip(ip, "a210.endpoint.three"):
            with self.assertRaises(frappe.RateLimitExceededError) as raised:
                resolve_driver_token(bogus)

        self.assertEqual(getattr(raised.exception, "http_status_code", None), 429)
        self.assertEqual(
            int(frappe.cache.get(frappe.cache.make_key(name)) or 0),
            limit + 1,
            "three endpoints must have charged one window, not three",
        )

    def test_bad_token_windows_are_independent_per_ip(self):
        """The ceiling is PER IP, and one address must never spend another's.

        One address exhausting its window must not lock a second address out —
        otherwise a single abuser would deny the portal to every worker behind
        every other connection. Proved two ways in one window: the second address
        still gets its ordinary 403, and the counter is shown to be keyed by remote
        address rather than being one global counter.
        """
        limit = token_security.BAD_TOKEN_ATTEMPTS_PER_MINUTE
        bogus = "definitely-not-a-real-token"
        cmd = "portal-security-perip-" + frappe.generate_hash(length=12)
        ip_a, ip_b = _fresh_ip(), _fresh_ip()
        keys = {ip: frappe.cache.make_key(self._window_name(ip)) for ip in (ip_a, ip_b)}
        for ip in (ip_a, ip_b):
            self._clean_window(ip)

        frappe.set_user("Guest")
        with _request_from_ip(ip_a, cmd):
            for _ in range(limit):
                with self.assertRaises(frappe.PermissionError):
                    resolve_driver_token(bogus)
            with self.assertRaises(frappe.RateLimitExceededError) as raised:
                resolve_driver_token(bogus)
        self.assertEqual(getattr(raised.exception, "http_status_code", None), 429)
        self.assertEqual(
            int(frappe.cache.get(keys[ip_a]) or 0),
            limit + 1,
            "the throttle must have counted every failed attempt from this address",
        )
        self.assertFalse(
            frappe.cache.get(keys[ip_b]),
            "the second address must not have been charged for the first's attempts",
        )

        # The second address still answers with the ordinary 403 — the
        # exhausted window belonged to IP A alone.
        with _request_from_ip(ip_b, cmd):
            with self.assertRaises(frappe.PermissionError):
                resolve_driver_token(bogus)

    def test_employee_non_active_statuses_revoke_without_token_revival(self):
        for status in ("Inactive", "Suspended", "Left"):
            with self.subTest(status=status):
                frappe.get_doc("Employee", self.employee).db_set(
                    {"status": "Active", "relieving_date": None}
                )
                issued = issue_worker_link(self.employee)
                employee = frappe.get_doc("Employee", self.employee)
                employee.status = status
                if status == "Left":
                    employee.relieving_date = frappe.utils.today()
                employee.save(ignore_permissions=True)

                self.assertEqual(
                    frappe.db.get_value(
                        "Masar Worker Token", {"employee": self.employee}, "enabled"
                    ),
                    0,
                )
                employee.db_set({"status": "Active", "relieving_date": None})
                with self.assertRaises(frappe.PermissionError):
                    masar._resolve_worker(issued["token"])

    def test_employee_transfer_db_set_path_revokes_without_revival(self):
        issued = issue_worker_link(self.employee)
        employee = frappe.get_doc("Employee", self.employee)

        employee.db_set("status", "Left")

        self.assertEqual(
            frappe.db.get_value(
                "Masar Worker Token", {"employee": self.employee}, "enabled"
            ),
            0,
        )
        employee.db_set("status", "Active")
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(issued["token"])

    def test_employee_inactivity_revokes_linked_driver_token(self):
        driver = self._make_driver(employee=self.employee)
        worker_issued = issue_worker_link(self.employee)
        driver_issued = issue_driver_link(driver)

        frappe.get_doc("Employee", self.employee).db_set("status", "Suspended")

        rows = frappe.get_all(
            "Masar Worker Token",
            filters={"name": ["in", [self.employee, driver]]},
            fields=["holder_type", "enabled"],
        )
        self.assertEqual(
            {row.holder_type: row.enabled for row in rows},
            {"Worker": 0, "Driver": 0},
        )
        frappe.get_doc("Employee", self.employee).db_set("status", "Active")
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(worker_issued["token"])
        with self.assertRaises(frappe.PermissionError):
            resolve_driver_token(driver_issued["token"])

    def test_driver_non_active_statuses_revoke_without_token_revival(self):
        """Salis Driver refuses a hand-written status edit through the document API
        (salis_driver.py:_refuse_a_hand_written_status), so every sanctioned writer
        sets it with ``frappe.db.set_value`` and pairs the raw write with an explicit
        revoke call -- Driver Suspension's submit is the "Stopped" example
        (portal_identity.py:on_driver_suspension_submit). This drives that same
        pairing directly against ``on_salis_driver_change`` to grade the revocation
        rule itself, independently of which document performs the write.

        "On Leave" is no longer one of Salis Driver's status options:
        patches/v2_6/converge_state_contracts.py folds it into "Stopped", and
        salis_driver/test_salis_driver_state_contract.py asserts it absent from the
        state list -- so only the two live statuses are driven here.
        """
        for status in ("Stopped", "Released"):
            with self.subTest(status=status):
                frappe.db.set_value("Salis Driver", self.driver, "status", "Active")
                issued = issue_driver_link(self.driver)
                frappe.db.set_value("Salis Driver", self.driver, "status", status)
                token_security.on_salis_driver_change(
                    frappe.get_doc("Salis Driver", self.driver)
                )

                self.assertEqual(
                    frappe.db.get_value(
                        "Masar Worker Token", {"driver": self.driver}, "enabled"
                    ),
                    0,
                )
                frappe.db.set_value("Salis Driver", self.driver, "status", "Active")
                with self.assertRaises(frappe.PermissionError):
                    resolve_driver_token(issued["token"])

    def test_driver_suspension_submit_and_cancel_never_revive_old_token(self):
        issued = issue_driver_link(self.driver)
        suspension = frappe.get_doc(
            {
                "doctype": "Driver Suspension",
                "driver": self.driver,
                "stop_reason": "Leave",
                "stop_date": frappe.utils.today(),
            }
        ).insert(ignore_permissions=True)

        suspension.submit()

        self.assertEqual(
            frappe.db.get_value("Salis Driver", self.driver, "status"), "Stopped"
        )
        self.assertEqual(
            frappe.db.get_value(
                "Masar Worker Token", {"driver": self.driver}, "enabled"
            ),
            0,
        )
        suspension.cancel()
        self.assertEqual(
            frappe.db.get_value("Salis Driver", self.driver, "status"), "Active"
        )
        with self.assertRaises(frappe.PermissionError):
            resolve_driver_token(issued["token"])

    def test_revocation_is_idempotent_and_exactly_audience_scoped(self):
        worker = self._worker_token()
        driver = self._driver_token()

        self.assertEqual(
            token_security.revoke_subject_tokens(token_security.WORKER, self.employee),
            1,
        )
        self.assertEqual(
            token_security.revoke_subject_tokens(token_security.WORKER, self.employee),
            0,
        )
        self.assertEqual(
            frappe.db.get_value("Masar Worker Token", driver.name, "enabled"), 1
        )
        self.assertEqual(
            token_security.revoke_subject_tokens(token_security.DRIVER, self.driver),
            1,
        )
        self.assertEqual(
            token_security.revoke_subject_tokens(token_security.DRIVER, self.driver),
            0,
        )
        self.assertEqual(
            frappe.db.get_value("Masar Worker Token", worker.name, "enabled"), 0
        )

    def test_inactive_subjects_cannot_use_singular_batch_or_direct_issuance(self):
        denied = (
            ("worker singular", "Worker", issue_worker_link),
            (
                "worker batch",
                "Worker",
                lambda subject: batch_issue_worker_links(json.dumps([subject])),
            ),
            ("worker direct", "Worker", get_or_create_for_employee),
            ("driver singular", "Driver", issue_driver_link),
            (
                "driver batch",
                "Driver",
                lambda subject: batch_issue_driver_links(json.dumps([subject])),
            ),
            ("driver direct", "Driver", get_or_create_for_driver),
        )
        for label, audience, operation in denied:
            if audience == "Worker":
                subject = self._make_employee()
                frappe.db.set_value("Employee", subject, "status", "Inactive")
                subject_field = "employee"
            else:
                subject = self._make_driver()
                frappe.db.set_value("Salis Driver", subject, "status", "On Leave")
                subject_field = "driver"
            with self.subTest(operation=label), self.assertRaises(
                frappe.PermissionError
            ):
                operation(subject)
            self.assertFalse(
                frappe.db.exists("Masar Worker Token", {subject_field: subject})
            )

    def test_inactive_subject_blocks_recover_extend_and_rotate(self):
        worker = self._worker_token()
        driver = self._driver_token()
        frappe.db.set_value("Employee", self.employee, "status", "Suspended")
        frappe.db.set_value("Salis Driver", self.driver, "status", "Released")

        for doc, operation in (
            (worker, "recover_token"),
            (worker, "extend_expiry"),
            (worker, "regenerate"),
            (driver, "recover_token"),
            (driver, "extend_expiry"),
            (driver, "regenerate"),
        ):
            with self.subTest(audience=doc.holder_type, operation=operation), self.assertRaises(
                frappe.PermissionError
            ):
                getattr(doc, operation)()

    def test_explicit_reissue_rotates_and_only_new_tokens_resolve(self):
        first_worker = issue_worker_link(self.employee)
        first_driver = issue_driver_link(self.driver)
        token_security.revoke_subject_tokens(token_security.WORKER, self.employee)
        token_security.revoke_subject_tokens(token_security.DRIVER, self.driver)

        second_worker = issue_worker_link(self.employee)
        second_driver = issue_driver_link(self.driver)

        self.assertNotEqual(second_worker["token"], first_worker["token"])
        self.assertNotEqual(second_driver["token"], first_driver["token"])
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(first_worker["token"])
        with self.assertRaises(frappe.PermissionError):
            resolve_driver_token(first_driver["token"])
        self.assertEqual(
            masar._resolve_worker(second_worker["token"]), self.employee
        )
        self.assertEqual(resolve_driver_token(second_driver["token"]), self.driver)

    def test_revoked_credentials_reject_direct_enable_without_rotation(self):
        cases = (
            (
                token_security.WORKER,
                self.employee,
                "employee",
                issue_worker_link,
                masar._resolve_worker,
            ),
            (
                token_security.DRIVER,
                self.driver,
                "driver",
                issue_driver_link,
                resolve_driver_token,
            ),
        )
        for audience, subject, subject_field, issue, resolve in cases:
            with self.subTest(audience=audience):
                issued = issue(subject)
                token_security.revoke_subject_tokens(audience, subject)
                name = frappe.db.get_value(
                    "Masar Worker Token",
                    {"holder_type": audience, subject_field: subject},
                    "name",
                )
                doc = frappe.get_doc("Masar Worker Token", name)
                persisted = frappe.db.get_value(
                    "Masar Worker Token",
                    name,
                    ["enabled", "token", "token_enc"],
                    as_dict=True,
                )

                doc.enabled = 1
                with self.assertRaises(frappe.PermissionError):
                    doc.save()

                current = frappe.db.get_value(
                    "Masar Worker Token",
                    name,
                    ["enabled", "token", "token_enc"],
                    as_dict=True,
                )
                self.assertEqual(current, persisted)
                doc.reload()
                with self.assertRaises(frappe.PermissionError):
                    doc.db_set("enabled", 1)
                self.assertEqual(
                    frappe.db.get_value("Masar Worker Token", name, "enabled"),
                    0,
                )
                with self.assertRaises(frappe.PermissionError):
                    resolve(issued["token"])

    def test_revoked_credentials_reject_direct_credential_replacement(self):
        cases = (
            (token_security.WORKER, self.employee, "employee", issue_worker_link),
            (token_security.DRIVER, self.driver, "driver", issue_driver_link),
        )
        for audience, subject, subject_field, issue in cases:
            with self.subTest(audience=audience):
                issue(subject)
                token_security.revoke_subject_tokens(audience, subject)
                name = frappe.db.get_value(
                    "Masar Worker Token",
                    {"holder_type": audience, subject_field: subject},
                    "name",
                )
                doc = frappe.get_doc("Masar Worker Token", name)
                persisted = frappe.db.get_value(
                    "Masar Worker Token",
                    name,
                    ["enabled", "token", "token_enc"],
                    as_dict=True,
                )
                replacement = frappe.generate_hash(length=48)
                doc.enabled = 1
                doc.token = _hash_token(replacement)
                doc.token_enc = encrypt(replacement)

                with self.assertRaises(frappe.PermissionError):
                    doc.save()

                current = frappe.db.get_value(
                    "Masar Worker Token",
                    name,
                    ["enabled", "token", "token_enc"],
                    as_dict=True,
                )
                self.assertEqual(current, persisted)

    def test_stale_cached_db_set_cannot_reenable_revoked_credentials(self):
        cases = (
            (
                token_security.WORKER,
                self.employee,
                "employee",
                issue_worker_link,
                masar._resolve_worker,
            ),
            (
                token_security.DRIVER,
                self.driver,
                "driver",
                issue_driver_link,
                resolve_driver_token,
            ),
        )
        for audience, subject, subject_field, issue, resolve in cases:
            with self.subTest(audience=audience):
                issued = issue(subject)
                name = frappe.db.get_value(
                    "Masar Worker Token",
                    {"holder_type": audience, subject_field: subject},
                    "name",
                )
                doc = frappe.get_doc("Masar Worker Token", name)
                doc.load_doc_before_save()
                self.assertEqual(doc.get_doc_before_save().enabled, 1)
                token_security.revoke_subject_tokens(audience, subject)
                self.assertEqual(
                    frappe.db.get_value("Masar Worker Token", name, "enabled"),
                    0,
                )

                persisted = frappe.db.get_value(
                    "Masar Worker Token",
                    name,
                    ["enabled", "token", "token_enc"],
                    as_dict=True,
                )
                forged = frappe.generate_hash(length=48)
                # The bare re-enable and the forged-credential install are one branch, not
                # two cases: db_set never sets _credential_reissue_guard, so `rotated` is
                # False at masar_worker_token.py:160 before the payload is ever compared,
                # and both land on the throw at :178. Kept as two db_set SHAPES here so
                # neither payload is lost.
                for label, payload, presented in (
                    ("re-enable only", {"enabled": 1}, issued["token"]),
                    (
                        "re-enable with a forged token",
                        {"enabled": 1, "token": _hash_token(forged)},
                        forged,
                    ),
                ):
                    with self.subTest(audience=audience, db_set=label):
                        savepoint = f"stale_{audience.lower()}_{len(payload)}"
                        frappe.db.savepoint(savepoint)
                        try:
                            with self.assertRaises(frappe.PermissionError):
                                doc.db_set(payload)
                            self.assertEqual(
                                frappe.db.get_value(
                                    "Masar Worker Token",
                                    name,
                                    ["enabled", "token", "token_enc"],
                                    as_dict=True,
                                ),
                                persisted,
                                "a refused db_set still wrote part of the credential",
                            )
                            with self.assertRaises(frappe.PermissionError):
                                resolve(presented)
                        finally:
                            frappe.db.rollback(save_point=savepoint)

    @timeout(15, "Portal issuance did not hold the subject row lock")
    def test_issue_status_race_serializes_on_subject_row(self):
        frappe.db.commit()
        self.addCleanup(frappe.db.rollback)

        with self.primary_connection():
            issued = issue_worker_link(self.employee)
            self.assertEqual(masar._resolve_worker(issued["token"]), self.employee)
            with self.secondary_connection(), self.assertRaises(
                frappe.QueryTimeoutError
            ):
                frappe.db.get_value(
                    "Employee",
                    self.employee,
                    "name",
                    for_update=True,
                    wait=False,
                )
            with self.primary_connection():
                frappe.db.commit()

        with self.secondary_connection():
            frappe.get_doc("Employee", self.employee).db_set(
                "status", "Inactive"
            )
            frappe.db.commit()

        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(issued["token"])

    def test_housing_roles_cannot_issue_driver_credentials(self):
        for role in (
            "Accommodation Manager",
            "Resident Supervisor",
            "HR User",
        ):
            with self.subTest(role=role):
                user = self._make_user(role)
                with _as_user(user), self.assertRaises(
                    frappe.PermissionError
                ) as error:
                    issue_driver_link(self._make_driver())
                self.assertIn("Driver", str(error.exception))

    def test_fleet_roles_cannot_issue_worker_credentials(self):
        for role in (
            "Fleet Manager",
            "Fleet Project Manager",
            "Fleet Supervisor",
        ):
            with self.subTest(role=role):
                user = self._make_user(role)
                employee = self._make_employee()
                with _as_user(user), self.assertRaises(
                    frappe.PermissionError
                ) as error:
                    issue_worker_link(employee)
                self.assertIn("Worker", str(error.exception))

    def test_resident_supervisor_requires_current_allowed_building(self):
        allowed_building = self._make_building()
        foreign_building = self._make_building()
        user = self._make_user(
            "Resident Supervisor",
            allow="Building",
            for_value=allowed_building,
        )
        employee = self._make_employee()
        self._house(employee, foreign_building)

        with _as_user(user), self.assertRaises(frappe.PermissionError) as error:
            issue_worker_link(employee)

        # frappe._() renders through the site's active language (portal_identity.py:493
        # msgid "Worker credential issuance requires an allowed Building."), so the raw
        # English word is not a reliable substring once a translation exists for it;
        # comparing against the same call proves this is the building-scope denial and
        # not some other PermissionError, in whatever language the site renders it.
        self.assertEqual(
            str(error.exception),
            frappe._("Worker credential issuance requires an allowed Building."),
        )

    def test_resident_supervisor_can_issue_current_allowed_building(self):
        building = self._make_building()
        user = self._make_user(
            "Resident Supervisor", allow="Building", for_value=building
        )
        employee = self._make_employee()
        self._house(employee, building)

        with _as_user(user):
            issued = issue_worker_link(employee)

        self.assertEqual(issued["employee"], employee)
        self.assertEqual(masar._resolve_worker(issued["token"]), employee)
        persisted = frappe.db.get_value(
            "Masar Worker Token",
            {"employee": employee},
            ["token", "expires_on"],
            as_dict=True,
        )
        self.assertEqual(persisted.token, _hash_token(issued["token"]))
        self.assertTrue(persisted.expires_on)

    def test_scoped_fleet_issuer_requires_driver_project(self):
        allowed_project = self._make_project()
        foreign_project = self._make_project()
        user = self._make_user(
            "Fleet Supervisor", allow="Project", for_value=allowed_project
        )
        driver = self._make_driver(project=foreign_project)

        with _as_user(user), self.assertRaises(frappe.PermissionError) as error:
            issue_driver_link(driver)

        # Same reasoning as the Building case above: portal_identity.py:506 renders
        # through frappe._(), so match the same call rather than an English substring.
        self.assertEqual(
            str(error.exception),
            frappe._("Driver credential issuance requires an allowed Project."),
        )

    def test_scoped_fleet_issuer_can_issue_allowed_driver_project(self):
        project = self._make_project()
        user = self._make_user(
            "Fleet Supervisor", allow="Project", for_value=project
        )
        driver = self._make_driver(project=project)

        with _as_user(user):
            issued = issue_driver_link(driver)

        self.assertEqual(issued["driver"], driver)
        persisted = frappe.db.get_value(
            "Masar Worker Token",
            {"driver": driver},
            [
                "token",
                "expires_on",
                "holder_type",
                "party_type",
                "party",
                "employee",
                "driver",
            ],
            as_dict=True,
        )
        self.assertEqual(persisted.token, _hash_token(issued["token"]))
        self.assertTrue(persisted.expires_on)
        self.assertEqual(
            {
                "holder_type": persisted.holder_type,
                "party_type": persisted.party_type,
                "party": persisted.party,
                "employee": persisted.employee,
                "driver": persisted.driver,
            },
            {
                "holder_type": "Driver",
                "party_type": None,
                "party": None,
                "employee": None,
                "driver": driver,
            },
        )
        self.assertEqual(resolve_driver_token(issued["token"]), driver)

    def test_fleet_manager_can_issue_unscoped_driver_credential(self):
        user = self._make_user("Fleet Manager")
        driver = self._make_driver()

        with _as_user(user):
            issued = issue_driver_link(driver)

        self.assertEqual(resolve_driver_token(issued["token"]), driver)

    def test_fleet_project_manager_can_issue_allowed_driver_project(self):
        project = self._make_project()
        user = self._make_user(
            "Fleet Project Manager", allow="Project", for_value=project
        )
        driver = self._make_driver(project=project)

        with _as_user(user):
            issued = issue_driver_link(driver)

        self.assertEqual(resolve_driver_token(issued["token"]), driver)

    def test_batch_worker_issuance_rejects_all_before_mutation(self):
        allowed_building = self._make_building()
        foreign_building = self._make_building()
        user = self._make_user(
            "Resident Supervisor",
            allow="Building",
            for_value=allowed_building,
        )
        allowed_employee = self._make_employee()
        foreign_employee = self._make_employee()
        self._house(allowed_employee, allowed_building)
        self._house(foreign_employee, foreign_building)

        with _as_user(user), self.assertRaises(frappe.PermissionError):
            batch_issue_worker_links(
                json.dumps([allowed_employee, foreign_employee])
            )

        self.assertFalse(
            frappe.db.exists(
                "Masar Worker Token", {"employee": allowed_employee}
            )
        )
        self.assertFalse(
            frappe.db.exists(
                "Masar Worker Token", {"employee": foreign_employee}
            )
        )

    def test_batch_driver_issuance_rejects_all_before_mutation(self):
        allowed_project = self._make_project()
        foreign_project = self._make_project()
        user = self._make_user(
            "Fleet Supervisor", allow="Project", for_value=allowed_project
        )
        allowed_driver = self._make_driver(project=allowed_project)
        foreign_driver = self._make_driver(project=foreign_project)

        with _as_user(user), self.assertRaises(frappe.PermissionError):
            batch_issue_driver_links(
                json.dumps([allowed_driver, foreign_driver])
            )

        self.assertFalse(
            frappe.db.exists("Masar Worker Token", {"driver": allowed_driver})
        )
        self.assertFalse(
            frappe.db.exists("Masar Worker Token", {"driver": foreign_driver})
        )

    def test_scoped_worker_reshare_rotates_instead_of_recovering(self):
        building = self._make_building()
        employee = self._make_employee()
        self._house(employee, building)
        first = issue_worker_link(employee)
        user = self._make_user(
            "Resident Supervisor", allow="Building", for_value=building
        )

        with _as_user(user):
            second = issue_worker_link(employee)

        self.assertNotEqual(second["token"], first["token"])
        old_row = frappe.db.get_value(
            "Masar Worker Token",
            {"token": _hash_token(first["token"])},
            ["name", "employee", "token"],
            as_dict=True,
        )
        new_row = frappe.db.get_value(
            "Masar Worker Token",
            {"token": _hash_token(second["token"])},
            ["name", "employee", "token"],
            as_dict=True,
        )
        self.assertFalse(old_row, f"old={old_row!r}; new={new_row!r}")
        self.assertTrue(
            frappe.db.exists(
                "Masar Worker Token", {"token": _hash_token(second["token"])}
            )
        )
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(first["token"])

    def test_resident_supervisor_can_reissue_disabled_worker_with_rotation(self):
        building = self._make_building()
        employee = self._make_employee()
        self._house(employee, building)
        first = issue_worker_link(employee)
        token_security.revoke_subject_tokens(token_security.WORKER, employee)
        user = self._make_user(
            "Resident Supervisor", allow="Building", for_value=building
        )

        with _as_user(user):
            second = issue_worker_link(employee)

        self.assertNotEqual(second["token"], first["token"])
        persisted = frappe.db.get_value(
            "Masar Worker Token",
            {"holder_type": "Worker", "employee": employee},
            ["enabled", "token"],
            as_dict=True,
        )
        self.assertEqual(persisted.enabled, 1)
        self.assertEqual(persisted.token, _hash_token(second["token"]))
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(first["token"])
        self.assertEqual(masar._resolve_worker(second["token"]), employee)

    # The driver twins of the two cases above — `test_scoped_driver_reshare_rotates_and_persists`,
    # `test_fleet_supervisor_can_reissue_disabled_driver_with_rotation` — are not defined here:
    # both branches live in `_issue_token` (masar_worker_token.py:445-468), holder-agnostic by
    # its own docstring, reading only doc.enabled / doc.token. What IS audience-specific
    # survives in `test_explicit_reissue_rotates_and_only_new_tokens_resolve` (revoke ->
    # reissue -> only the new token resolves, both audiences) and
    # `test_scoped_fleet_issuer_can_issue_allowed_driver_project`.

    def test_scoped_issuer_can_persist_expiry_extension(self):
        building = self._make_building()
        employee = self._make_employee()
        self._house(employee, building)
        issue_worker_link(employee)
        expired = frappe.utils.add_to_date(
            frappe.utils.now_datetime(), days=-1
        )
        frappe.db.set_value(
            "Masar Worker Token", employee, "expires_on", expired
        )
        user = self._make_user(
            "Resident Supervisor", allow="Building", for_value=building
        )

        with _as_user(user):
            doc = frappe.get_doc("Masar Worker Token", employee)
            extended = doc.extend_expiry()

        persisted = frappe.db.get_value(
            "Masar Worker Token", employee, "expires_on"
        )
        self.assertGreater(frappe.utils.get_datetime(persisted), expired)
        self.assertEqual(
            frappe.utils.get_datetime(persisted),
            frappe.utils.get_datetime(extended),
        )

    def test_cross_domain_direct_insert_is_denied(self):
        resident = self._make_user("Resident Supervisor")
        driver = self._make_driver()
        with _as_user(resident), self.assertRaises(frappe.PermissionError):
            frappe.get_doc(
                {
                    "doctype": "Masar Worker Token",
                    "holder_type": "Driver",
                    "driver": driver,
                }
            ).insert(ignore_permissions=True)

    def test_metadata_grants_exact_fleet_issuer_docperms(self):
        doctype_path = TOKEN_METADATA
        metadata = json.loads(doctype_path.read_text(encoding="utf-8"))
        permissions = {
            row["role"]: row
            for row in metadata["permissions"]
            if not row.get("permlevel")
        }

        for role in ("Fleet Manager", "Fleet Project Manager"):
            self.assertTrue(permissions[role]["create"])
            self.assertTrue(permissions[role]["read"])
            self.assertTrue(permissions[role]["write"])
            self.assertTrue(permissions[role]["report"])
            self.assertTrue(permissions[role]["print"])
