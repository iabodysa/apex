# Copyright (c) 2026, AFMCO and contributors
"""Adversarial coverage for worker and driver portal bearer isolation."""

import base64
from contextlib import contextmanager
from io import BytesIO
import inspect
import json
from pathlib import Path
import zlib
from urllib.parse import parse_qs, urlparse
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase, timeout
from frappe.utils.password import encrypt
from PIL import Image

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
from apex.apex_core.utils import portal_token_security as token_security
from apex.salis.api import boarding, driver_portal, masar
from apex.salis.api.driver_portal import (
    boarding as driver_boarding,
    clearance,
    fuel,
    images,
    notifications,
    profile,
    support,
    trips,
)
from apex.www import driver as driver_page, masar as masar_page


def _image_data_uri(image_format="PNG"):
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color=(12, 34, 56)).save(
        buffer,
        format=image_format,
    )
    mime = {"JPEG": "jpeg", "PNG": "png", "WEBP": "webp"}[image_format]
    return "data:image/" + mime + ";base64," + base64.b64encode(buffer.getvalue()).decode()


def _image_bytes(image_format="PNG"):
    return base64.b64decode(_image_data_uri(image_format).split(",", 1)[1])


def _compact_png_with_dimensions(width, height):
    """Rewrite only PNG IHDR dimensions, keeping the payload compact."""
    payload = bytearray(_image_bytes("PNG"))
    payload[16:20] = width.to_bytes(4, "big")
    payload[20:24] = height.to_bytes(4, "big")
    payload[29:33] = zlib.crc32(payload[12:29]).to_bytes(4, "big")
    return "data:image/png;base64," + base64.b64encode(payload).decode()


def _fresh_ip():
    """An address no other block can be using: the RFC 3849 documentation prefix
    plus a random suffix. Needed because the bad-token window is keyed on the
    ADDRESS ALONE, so a shared 127.0.0.1 would let one test's failed tokens spend
    another test's budget."""
    return "2001:db8::" + frappe.generate_hash(length=12)


class _Request:
    def __init__(self, cookies, remote_addr="127.0.0.1"):
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


@contextmanager
def _form_dict(values):
    sentinel = object()
    previous = getattr(frappe.local, "form_dict", sentinel)
    frappe.local.form_dict = frappe._dict(values)
    try:
        yield
    finally:
        if previous is sentinel:
            if hasattr(frappe.local, "form_dict"):
                delattr(frappe.local, "form_dict")
        else:
            frappe.local.form_dict = previous


class _as_user:
    def __init__(self, user):
        self.user = user

    def __enter__(self):
        self.previous = frappe.session.user
        frappe.set_user(self.user)
        token_meta = frappe.get_meta("Masar Worker Token")
        self.previous_autoname = token_meta.autoname
        self.previous_permissions = token_meta.permissions
        doctype_path = (
            Path(__file__).resolve().parents[1]
            / "apex_core"
            / "doctype"
            / "masar_worker_token"
            / "masar_worker_token.json"
        )
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


def _notification_log_only(rows=None):
    """A get_all side_effect that returns ``rows`` for the Notification Log query and
    delegates every other call to the real get_all. In developer_mode get_meta rebuilds
    each call via get_all, so a blanket get_all patch would also swallow those meta reads."""
    real = frappe.get_all

    def _side_effect(*args, **kwargs):
        doctype = args[0] if args else kwargs.get("doctype")
        if doctype == "Notification Log":
            return list(rows or [])
        return real(*args, **kwargs)

    return _side_effect


class TestPortalTokenSecurity(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        self.employee = self._make_employee()
        self.driver = self._make_driver()
        token_meta = frappe.get_meta("Masar Worker Token")
        self._original_autoname = token_meta.autoname
        self._original_permissions = token_meta.permissions
        doctype_path = (
            Path(__file__).resolve().parents[1]
            / "apex_core"
            / "doctype"
            / "masar_worker_token"
            / "masar_worker_token.json"
        )
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
        if allow and for_value:
            frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "user": user,
                    "allow": allow,
                    "for_value": for_value,
                }
            ).insert(ignore_permissions=True)
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

    def test_bootstrap_without_credential_returns_only_friendly_configuration(self):
        frappe.set_user("Guest")
        with _request_cookies({}):
            result = profile.get_driver_context()
        self.assertEqual(result["driver"], None)
        self.assertFalse(result["linked"])
        self.assertEqual(result["links"], [])
        self.assertTrue(
            set(result).issubset(
                {"enabled", "linked", "driver", "is_staff", "full_name", "links"}
            )
        )

    def test_disabled_bootstrap_validates_a_presented_driver_credential_first(self):
        previous = frappe.db.get_single_value(
            "Salis Settings", "enable_driver_portal"
        )
        frappe.db.set_single_value(
            "Salis Settings", "enable_driver_portal", 0
        )
        frappe.set_user("Guest")
        try:
            with _request_cookies({"masar_dt": "invalid-driver-credential"}), patch.object(
                profile, "_is_staff"
            ) as staff, patch.object(profile, "_user_full_name") as full_name:
                with self.assertRaises(frappe.PermissionError):
                    profile.get_driver_context()
            staff.assert_not_called()
            full_name.assert_not_called()
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_single_value(
                "Salis Settings", "enable_driver_portal", previous
            )

    def test_foreign_push_endpoint_cannot_be_rebound(self):
        self._configure_push()
        token = self._driver_token()
        foreign_driver = self._make_driver()
        endpoint = "https://fcm.googleapis.com/fcm/send/foreign-owner"
        subscription = frappe.get_doc(
            {
                "doctype": "Driver Push Subscription",
                "driver": foreign_driver,
                "endpoint": endpoint,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)

        frappe.set_user("Guest")
        with _request_cookies({"masar_dt": token._plaintext_token}):
            with self.assertRaises(frappe.PermissionError):
                driver_portal.save_push_subscription(endpoint=endpoint)

        self.assertEqual(
            frappe.db.get_value("Driver Push Subscription", subscription.name, "driver"),
            foreign_driver,
        )

    def test_push_state_is_scoped_by_driver_without_guest_user_filter(self):
        self._configure_push()
        token = self._driver_token()
        frappe.get_doc(
            {
                "doctype": "Driver Push Subscription",
                "driver": self.driver,
                "endpoint": "https://fcm.googleapis.com/fcm/send/driver-state",
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)

        frappe.set_user("Guest")
        with _request_cookies({"masar_dt": token._plaintext_token}):
            result = notifications.get_push_config()
        self.assertTrue(result["enabled"])
        self.assertTrue(result["subscribed"])

    def test_notifications_without_driver_user_never_query_guest_log(self):
        token = self._driver_token()
        self.assertFalse(
            frappe.db.get_value("Salis Driver", self.driver, "driver_user")
        )

        frappe.set_user("Guest")
        with _request_cookies({"masar_dt": token._plaintext_token}), patch.object(
            notifications.frappe, "get_all", side_effect=_notification_log_only()
        ) as notification_query:
            result = notifications.get_my_notifications()

        self.assertEqual(result, [])
        guest_log_queries = [
            call
            for call in notification_query.call_args_list
            if call.args and call.args[0] == "Notification Log"
        ]
        self.assertEqual(guest_log_queries, [])

    def test_notifications_with_guest_as_driver_user_never_query_guest_log(self):
        token = self._driver_token()
        frappe.db.set_value("Salis Driver", self.driver, "driver_user", "Guest")

        frappe.set_user("Guest")
        with _request_cookies({"masar_dt": token._plaintext_token}), patch.object(
            notifications.frappe, "get_all", side_effect=_notification_log_only()
        ) as notification_query:
            result = notifications.get_my_notifications()

        self.assertEqual(result, [])
        guest_log_queries = [
            call
            for call in notification_query.call_args_list
            if call.args and call.args[0] == "Notification Log"
        ]
        self.assertEqual(guest_log_queries, [])

    def test_notifications_return_only_owned_driver_facing_records(self):
        token = self._driver_token()
        driver_user = self._make_user("HR Manager")
        frappe.db.set_value("Salis Driver", self.driver, "driver_user", driver_user)
        other_driver = self._make_driver()
        own_log = frappe.get_doc(
            {
                "doctype": "Notification Log",
                "for_user": driver_user,
                "type": "Alert",
                "subject": "Driver-only notification",
                "email_content": "Driver body",
                "document_type": "Salis Driver",
                "document_name": self.driver,
            }
        ).insert(ignore_permissions=True)
        excluded = [
            {
                "subject": "Other driver notification",
                "document_type": "Salis Driver",
                "document_name": other_driver,
            },
            {
                "subject": "Elevated user notification",
                "document_type": "User",
                "document_name": driver_user,
            },
            {
                "subject": "Unrelated employee notification",
                "document_type": "Employee",
                "document_name": self.employee,
            },
            {
                "subject": "Unreferenced notification",
            },
        ]
        for values in excluded:
            frappe.get_doc(
                {
                    "doctype": "Notification Log",
                    "for_user": driver_user,
                    "type": "Alert",
                    "email_content": "Must stay in Desk.",
                    **values,
                }
            ).insert(ignore_permissions=True)

        frappe.set_user("Guest")
        with _request_cookies({"masar_dt": token._plaintext_token}):
            result = notifications.get_my_notifications()

        self.assertEqual([row["name"] for row in result], [own_log.name])
        self.assertEqual(
            set(result[0]),
            {"name", "subject", "body", "read", "creation"},
        )

    def test_notifications_bound_candidates_before_ownership_checks(self):
        token = self._driver_token()
        driver_user = self._make_user("HR Manager")
        frappe.db.set_value("Salis Driver", self.driver, "driver_user", driver_user)
        candidate = frappe._dict(
            name="NL-CANDIDATE",
            subject="Candidate",
            email_content="Body",
            read=0,
            creation=frappe.utils.now_datetime(),
            document_type="Salis Driver",
            document_name=self.driver,
        )

        frappe.set_user("Guest")
        real_exists = notifications.frappe.db.exists
        with _request_cookies({"masar_dt": token._plaintext_token}), patch.object(
            notifications.frappe, "get_all", side_effect=_notification_log_only([candidate])
        ) as query, patch.object(
            notifications.frappe.db, "exists", wraps=real_exists
        ) as ownership_checks:
            result = notifications.get_my_notifications(limit=20)

        self.assertEqual([row["name"] for row in result], ["NL-CANDIDATE"])
        notification_queries = [
            call
            for call in query.call_args_list
            if call.args and call.args[0] == "Notification Log"
        ]
        self.assertEqual(len(notification_queries), 1)
        args, kwargs = notification_queries[0]
        self.assertEqual(
            kwargs["filters"]["document_type"],
            ["in", ["Salis Driver", "Dispatch Trip", "Salis Vehicle", "Driver Clearance"]],
        )
        self.assertEqual(kwargs["order_by"], "creation desc")
        self.assertLessEqual(kwargs["limit"], 250)
        self.assertIn("document_type", kwargs["fields"])
        self.assertIn("document_name", kwargs["fields"])
        self.assertLessEqual(ownership_checks.call_count, kwargs["limit"])

    def test_clearance_get_is_read_only_and_certificate_post_reuses_finite_key(self):
        from frappe.www.printview import validate_key, validate_print_permission

        token = self._driver_token()
        own = self._cleared_clearance(self.driver)
        other_driver = self._make_driver()
        foreign = self._cleared_clearance(other_driver)
        frappe.db.set_value("Salis Driver", self.driver, "status", "Active")
        frappe.db.set_value("Masar Worker Token", token.name, "enabled", 1)

        frappe.set_user("Guest")
        with _request_cookies({"masar_dt": token._plaintext_token}):
            before = frappe.db.count(
                "Document Share Key",
                {"reference_doctype": "Driver Clearance", "reference_docname": own.name},
            )
            state = driver_portal.my_clearance()
            after = frappe.db.count(
                "Document Share Key",
                {"reference_doctype": "Driver Clearance", "reference_docname": own.name},
            )
            result = driver_portal.get_my_clearance_certificate()
            repeated = driver_portal.get_my_clearance_certificate()

        self.assertTrue(state["issued"])
        self.assertNotIn("certificate_url", state)
        self.assertEqual(before, after, "GET created a Document Share Key")
        self.assertEqual(result["certificate_url"], repeated["certificate_url"])

        query = parse_qs(urlparse(result["certificate_url"]).query)
        key = query["key"][0]
        self.assertEqual(query["doctype"], ["Driver Clearance"])
        self.assertEqual(query["name"], [own.name])
        share = frappe.db.get_value(
            "Document Share Key",
            {"key": key},
            ["reference_doctype", "reference_docname", "expires_on"],
            as_dict=True,
        )
        self.assertEqual(share.reference_doctype, "Driver Clearance")
        self.assertEqual(share.reference_docname, own.name)
        self.assertEqual(
            share.expires_on,
            frappe.utils.getdate(
                frappe.utils.add_days(frappe.utils.today(), 1)
            ),
        )

        frappe.set_user("Guest")
        with _form_dict({"key": key}):
            validate_print_permission(frappe.get_doc("Driver Clearance", own.name))
            self.assertFalse(validate_key(key, frappe.get_doc("Driver Clearance", foreign.name)))
            with self.assertRaises(frappe.PermissionError):
                validate_print_permission(frappe.get_doc("Driver Clearance", foreign.name))

        frappe.db.set_value(
            "Document Share Key",
            {"key": key},
            "expires_on",
            frappe.utils.add_days(frappe.utils.today(), -1),
        )
        with self.assertRaises(frappe.exceptions.LinkExpired):
            validate_key(key, frappe.get_doc("Driver Clearance", own.name))

        source = inspect.getsource(clearance)
        self.assertIn(
            '@frappe.whitelist(allow_guest=True, methods=["POST"])\n'
            '@rate_limit(key="frappe.request.remote_addr", limit=10, seconds=60)\n'
            "def get_my_clearance_certificate",
            source,
        )

    def test_clearance_certificate_serializes_exact_expiry_without_deleting_other_shares(self):
        token = self._driver_token()
        own = self._cleared_clearance(self.driver)
        other_driver = self._make_driver()
        foreign = self._cleared_clearance(other_driver)
        expired = frappe.utils.add_days(frappe.utils.today(), -1)
        future = frappe.utils.add_days(frappe.utils.today(), 2)
        for docname, expires_on in (
            (own.name, expired),
            (own.name, future),
            (foreign.name, expired),
        ):
            frappe.get_doc(
                {
                    "doctype": "Document Share Key",
                    "reference_doctype": "Driver Clearance",
                    "reference_docname": docname,
                    "expires_on": expires_on,
                }
            ).insert(ignore_permissions=True)

        frappe.set_user("Guest")
        real_get_value = clearance.frappe.db.get_value
        with _request_cookies({"masar_dt": token._plaintext_token}), patch.object(
            clearance.frappe.db, "get_value", wraps=real_get_value
        ) as reads:
            first = driver_portal.get_my_clearance_certificate()
            second = driver_portal.get_my_clearance_certificate()

        self.assertEqual(first["certificate_url"], second["certificate_url"])
        own_keys = frappe.get_all(
            "Document Share Key",
            filters={"reference_doctype": "Driver Clearance", "reference_docname": own.name},
            fields=["key", "expires_on"],
        )
        self.assertEqual(len(own_keys), 3)
        endpoint_expiry = frappe.utils.getdate(
            frappe.utils.add_days(frappe.utils.today(), 1)
        )
        endpoint_keys = [
            row for row in own_keys if row["expires_on"] == endpoint_expiry
        ]
        self.assertEqual(len(endpoint_keys), 1)
        self.assertTrue(
            any(call.kwargs.get("for_update") for call in reads.call_args_list),
            "certificate issuance must lock the resolved clearance row",
        )
        self.assertTrue(
            frappe.db.exists(
                "Document Share Key",
                {
                    "reference_doctype": "Driver Clearance",
                    "reference_docname": own.name,
                    "expires_on": expired,
                },
            ),
            "expired intentional shares must not be deleted by portal issuance",
        )
        self.assertTrue(
            frappe.db.exists(
                "Document Share Key",
                {
                    "reference_doctype": "Driver Clearance",
                    "reference_docname": own.name,
                    "expires_on": future,
                },
            ),
            "unrelated future shares must not be reused or deleted",
        )
        self.assertTrue(
            frappe.db.exists(
                "Document Share Key",
                {
                    "reference_doctype": "Driver Clearance",
                    "reference_docname": foreign.name,
                    "expires_on": expired,
                },
            ),
            "foreign clearance cleanup escaped the resolved driver's document",
        )

    def test_shared_photo_helper_validates_and_saves_private_file(self):
        helper_path = (
            Path(__file__).resolve().parents[1]
            / "salis"
            / "api"
            / "driver_portal"
            / "images.py"
        )
        self.assertTrue(helper_path.exists(), "shared driver image helper is missing")
        from apex.salis.api.driver_portal import images

        photo = _image_data_uri("PNG")
        expected = frappe._dict(file_url="/private/files/evidence.png")
        with patch.object(images, "save_file", return_value=expected) as save:
            result = images.save_driver_image(
                photo,
                "evidence.png",
                "Issue",
                "ISSUE-0001",
            )
        self.assertIs(result, expected)
        save.assert_called_once_with(
            "evidence.png",
            photo,
            "Issue",
            "ISSUE-0001",
            decode=True,
            is_private=1,
        )

    def test_shared_photo_helper_rejects_malformed_wrong_type_and_oversize(self):
        helper_path = (
            Path(__file__).resolve().parents[1]
            / "salis"
            / "api"
            / "driver_portal"
            / "images.py"
        )
        self.assertTrue(helper_path.exists(), "shared driver image helper is missing")
        from apex.salis.api.driver_portal import images

        with self.assertRaises(frappe.ValidationError):
            images.save_driver_image("not-base64", "evidence.png", "Issue", "I-1")
        with self.assertRaises(frappe.ValidationError):
            images.save_driver_image(
                "data:image/png;base64,eGFiYw==",
                "evidence.txt",
                "Issue",
                "I-1",
            )
        with self.assertRaises(frappe.ValidationError):
            images.save_driver_image(
                "data:image/jpeg;base64,eGFiYw==",
                "evidence.png",
                "Issue",
                "I-1",
            )
        with patch.object(images, "MAX_IMAGE_BYTES", 3), self.assertRaises(
            frappe.ValidationError
        ):
            images.save_driver_image(
                "data:image/png;base64," + base64.b64encode(b"four").decode(),
                "evidence.png",
                "Issue",
                "I-1",
            )

    def test_shared_photo_helper_rejects_content_mismatch_and_unsafe_names(self):
        from apex.salis.api.driver_portal import images

        malformed = [
            ("data:image/png;base64," + base64.b64encode(b"<html>not an image</html>").decode(), "evidence.png"),
            ("data:image/png;base64," + base64.b64encode(b"<svg xmlns='http://www.w3.org/2000/svg'/>").decode(), "evidence.png"),
            ("data:image/png;base64," + base64.b64encode(_image_bytes("PNG")[:-12]).decode(), "evidence.png"),
            ("data:image/jpeg;base64," + base64.b64encode(_image_bytes("PNG")).decode(), "evidence.jpg"),
            ("data:image/png;base64," + base64.b64encode(_image_bytes("PNG") + b"<script>polyglot</script>").decode(), "evidence.png"),
        ]
        unsafe_names = [
            "../evidence.png",
            "folder\\evidence.png",
            "evidence\n.png",
            ".evidence.png",
            "evidence?.png",
            "\u202eevidence.png",
            "e" * 129 + ".png",
        ]
        with patch.object(images, "save_file") as save:
            for photo, filename in malformed:
                with self.subTest(filename=filename, photo=photo[:30]):
                    with self.assertRaises(frappe.ValidationError):
                        images.save_driver_image(photo, filename, "Issue", "I-1")
            for filename in unsafe_names:
                with self.subTest(filename=filename):
                    with self.assertRaises(frappe.ValidationError):
                        images.save_driver_image(
                            _image_data_uri("PNG"),
                            filename,
                            "Issue",
                            "I-1",
                        )
        save.assert_not_called()

    def test_shared_photo_helper_accepts_real_jpeg_png_and_webp(self):
        from apex.salis.api.driver_portal import images

        expected = frappe._dict(file_url="/private/files/evidence")
        with patch.object(images, "save_file", return_value=expected) as save:
            for image_format, filename in (
                ("JPEG", "evidence.jpg"),
                ("PNG", "evidence.png"),
                ("WEBP", "evidence.webp"),
            ):
                with self.subTest(image_format=image_format):
                    self.assertIs(
                        images.save_driver_image(
                            _image_data_uri(image_format),
                            filename,
                            "Issue",
                            "I-1",
                        ),
                        expected,
                    )
        self.assertEqual(save.call_count, 3)

    def test_shared_photo_helper_rejects_dimension_and_decompression_bombs(self):
        for width, height in ((8193, 1), (1, 8193), (5000, 4001)):
            with self.subTest(width=width, height=height), self.assertRaises(
                frappe.ValidationError
            ):
                images.save_driver_image(
                    _compact_png_with_dimensions(width, height),
                    "bomb.png",
                    "Issue",
                    "I-1",
                )
        for bomb in (Image.DecompressionBombWarning, Image.DecompressionBombError):
            with self.subTest(bomb=bomb.__name__), patch.object(
                images.Image, "open", side_effect=bomb("bomb")
            ), self.assertRaises(frappe.ValidationError):
                images.save_driver_image(
                    _image_data_uri("PNG"), "bomb.png", "Issue", "I-1"
                )

    def test_shared_photo_helper_accepts_exact_dimension_boundaries(self):
        class BoundaryImage:
            format = "PNG"

            def __init__(self, size):
                self.size = size

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def verify(self):
                return None

        with patch.object(images, "save_file", return_value=frappe._dict()) as save:
            for size in ((8192, 1), (5000, 4000)):
                with self.subTest(size=size), patch.object(
                    images.Image, "open", return_value=BoundaryImage(size)
                ):
                    images.save_driver_image(
                        _image_data_uri("PNG"), "boundary.png", "Issue", "I-1"
                    )
        self.assertEqual(save.call_count, 2)

    def test_manual_boarding_rejects_non_list_non_scalar_and_over_cap_before_work(self):
        trip = frappe._dict(transport_request="TR-1")
        invalid_payloads = (
            json.dumps("EMP-1"),
            json.dumps(["EMP-1", {"employee": "EMP-2"}]),
            json.dumps(["EMP-1"] * 101),
        )
        with patch.object(driver_boarding, "_require_enabled"), patch.object(
            driver_boarding, "_resolve_driver", return_value=self.driver
        ), patch.object(
            boarding, "_resolve_trip", return_value=trip
        ), patch.object(
            boarding, "_trip_manifest_workers"
        ) as manifest, patch.object(
            boarding, "_get_or_create_log"
        ) as create_log:
            for payload in invalid_payloads:
                with self.subTest(payload=payload[:40]), self.assertRaises(
                    frappe.ValidationError
                ):
                    driver_boarding.manual_board_workers("DT-1", payload)

        manifest.assert_not_called()
        create_log.assert_not_called()

    def test_manual_boarding_stable_deduplicates_before_result_and_audit_logging(self):
        log = MagicMock(name="trip_start_log")
        log.name = "TSL-1"
        log.boarded_count = 1
        trip = frappe._dict(transport_request="TR-1")
        order = []
        with patch.object(driver_boarding, "_require_enabled"), patch.object(
            driver_boarding, "_resolve_driver", return_value=self.driver
        ), patch.object(
            boarding, "_resolve_trip", return_value=trip
        ), patch.object(
            driver_boarding.frappe.db,
            "get_value",
            side_effect=lambda *args, **kwargs: order.append("lock"),
        ) as trip_lock, patch.object(
            boarding,
            "_get_or_create_log",
            side_effect=lambda _dispatch_trip: order.append("log") or log,
        ), patch.object(
            boarding, "_trip_manifest_workers", return_value={"EMP-1"}
        ), patch.object(
            boarding, "_already_boarded", return_value=False
        ), patch.object(driver_boarding, "_log_manual_scan") as audit:
            result = driver_boarding.manual_board_workers(
                "DT-1", json.dumps(["EMP-1", "EMP-1"])
            )

        self.assertEqual(result["boarded"], ["EMP-1"])
        self.assertEqual(result["skipped"], [])
        self.assertEqual(log.append.call_count, 1)
        self.assertEqual(audit.call_count, 1)
        trip_lock.assert_called_once_with(
            "Dispatch Trip", "DT-1", "name", for_update=True
        )
        self.assertLess(order.index("lock"), order.index("log"))

    def test_support_text_caps_accept_boundaries_and_reject_one_character_over(self):
        issue = MagicMock(name="issue")
        issue.doctype = "Issue"
        issue.name = "ISSUE-1"
        with patch.object(support, "_driver_identity", return_value="driver@example.com"), patch.object(
            support.frappe.db, "get_value", return_value=None
        ), patch.object(
            support.frappe.db, "exists", return_value=False
        ), patch.object(
            support.frappe, "get_doc", return_value=issue
        ), patch.object(images, "save_driver_image"):
            support._create_support_ticket(
                self.driver,
                None,
                None,
                "S" * 140,
                "D" * 10_000,
            )
            for subject, description in (
                ("S" * 141, "Description"),
                ("Subject", "D" * 10_001),
            ):
                with self.subTest(
                    subject_length=len(subject), description_length=len(description)
                ), self.assertRaises(frappe.ValidationError):
                    support._create_support_ticket(
                        self.driver,
                        None,
                        None,
                        subject,
                        description,
                    )

        self.assertEqual(issue.insert.call_count, 1)

    def test_support_reply_cap_accepts_boundary_and_rejects_one_character_over(self):
        communication = MagicMock(name="communication")
        communication.name = "COMM-1"
        with patch.object(support, "_require_enabled"), patch.object(
            support, "_resolve_driver", return_value=self.driver
        ), patch.object(
            support, "_driver_identity", return_value="driver@example.com"
        ), patch.object(
            support, "_driver_issue", return_value=frappe._dict(subject="Issue", status="Open")
        ), patch.object(
            support.frappe, "get_doc", return_value=communication
        ) as get_doc:
            support.reply_to_ticket("ISSUE-1", "R" * 5_000)
            with self.assertRaises(frappe.ValidationError):
                support.reply_to_ticket("ISSUE-1", "R" * 5_001)

        self.assertEqual(get_doc.call_count, 1)
        self.assertEqual(get_doc.call_args.args[0]["content"], "R" * 5_000)

    def test_support_communications_use_capped_deterministic_offset_pagination(self):
        parameters = inspect.signature(support.get_ticket).parameters
        self.assertIn("communication_offset", parameters)
        self.assertIn("communication_limit", parameters)

        rows = [
            frappe._dict(
                name=f"COMM-{index:03d}",
                content="Reply",
                sender="driver@example.com",
                sent_or_received="Received",
                communication_date=None,
                creation=None,
            )
            for index in range(51)
        ]
        issue = frappe._dict(
            name="ISSUE-1",
            subject="Issue",
            description="Description",
            status="Open",
            category="Vehicle",
            priority="Medium",
            creation=None,
            response_by=None,
            resolution_by=None,
            first_responded_on=None,
            resolution_date=None,
        )
        with patch.object(support, "_require_enabled"), patch.object(
            support, "_resolve_driver", return_value=self.driver
        ), patch.object(
            support, "_driver_issue", return_value=issue
        ), patch.object(
            support.frappe, "get_all", return_value=rows
        ) as query:
            detail = support.get_ticket(
                "ISSUE-1", communication_offset=7, communication_limit=999
            )

        self.assertEqual(len(detail["communications"]), 50)
        self.assertTrue(detail["communication_has_more"])
        self.assertEqual(detail["communication_next_offset"], 57)
        query.assert_called_once()
        self.assertEqual(query.call_args.kwargs["limit_start"], 7)
        self.assertEqual(query.call_args.kwargs["limit"], 51)
        self.assertEqual(
            query.call_args.kwargs["order_by"],
            "communication_date asc, creation asc, name asc",
        )
        self.assertIn("creation", query.call_args.kwargs["fields"])

    def test_boarding_scan_rate_is_exactly_sixty_per_minute(self):
        self.assertEqual(boarding.SCAN_ACTOR_LIMIT, 60)
        self.assertEqual(boarding.SCAN_UNRESOLVED_IP_LIMIT, 60)

    def test_driver_history_inputs_are_clamped_to_positive_safe_caps(self):
        with patch.object(trips, "_require_enabled"), patch.object(
            trips, "_resolve_driver", return_value=self.driver
        ), patch.object(trips.frappe, "get_all", return_value=[]) as trip_query:
            trips.my_trips_recent(days=90, limit=100)
            self.assertEqual(trip_query.call_args.kwargs["limit"], 100)
            self.assertEqual(
                trip_query.call_args.kwargs["filters"]["trip_date"],
                [">=", frappe.utils.add_days(frappe.utils.today(), -90)],
            )
            trips.my_trips_recent(days="bad", limit=-5)
            self.assertEqual(trip_query.call_args.kwargs["limit"], 50)
            self.assertEqual(
                trip_query.call_args.kwargs["filters"]["trip_date"],
                [">=", frappe.utils.add_days(frappe.utils.today(), -30)],
            )
            trips.my_trips_recent(days=9999, limit=9999)
            self.assertEqual(trip_query.call_args.kwargs["limit"], 100)
            self.assertEqual(
                trip_query.call_args.kwargs["filters"]["trip_date"],
                [">=", frappe.utils.add_days(frappe.utils.today(), -90)],
            )

        with patch.object(fuel, "_require_enabled"), patch.object(
            fuel, "_resolve_driver", return_value=self.driver
        ), patch.object(fuel.frappe, "get_all", return_value=[]) as fuel_query:
            fuel.my_fuel_requests(limit=50)
            self.assertEqual(fuel_query.call_args.kwargs["limit"], 50)
            fuel.my_fuel_requests(limit=-1)
            self.assertEqual(fuel_query.call_args.kwargs["limit"], 30)
            fuel.my_fuel_requests(limit=9999)
            self.assertEqual(fuel_query.call_args.kwargs["limit"], 50)

    def test_support_photo_is_a_private_native_attachment_on_new_issue(self):
        parameters = inspect.signature(driver_portal.raise_support_ticket).parameters
        self.assertIn("photo_filename", parameters)
        token = self._driver_token()
        photo = _image_data_uri("PNG")
        frappe.set_user("Guest")
        with _request_cookies({"masar_dt": token._plaintext_token}):
            result = driver_portal.raise_support_ticket(
                "Vehicle",
                "Medium",
                "Guest driver issue",
                "Photo is attached directly.",
                photo=photo,
                photo_filename="issue.png",
            )
        attachment = frappe.db.get_value(
            "File",
            {"attached_to_doctype": "Issue", "attached_to_name": result["name"]},
            ["is_private", "file_url"],
            as_dict=True,
        )
        self.assertTrue(attachment)
        self.assertTrue(attachment.is_private)
        self.assertTrue(attachment.file_url.startswith("/private/files/"))
        self.assertEqual(
            frappe.db.get_value("Issue", result["name"], "raised_by"),
            frappe.scrub(self.driver).replace("_", "-") + "@driver.invalid",
        )

    def test_guest_support_timeline_uses_the_resolved_driver_identity(self):
        driver_user = self._make_user("Driver")
        frappe.db.set_value(
            "Salis Driver", self.driver, "driver_user", driver_user
        )
        token = self._driver_token()
        frappe.set_user("Guest")
        with _request_cookies({"masar_dt": token._plaintext_token}):
            issue_name = driver_portal.raise_support_ticket(
                "Vehicle",
                "Medium",
                "Credential-attributed issue",
                "Created without session impersonation.",
            )["name"]
            self.assertEqual(frappe.session.user, "Guest")
            communication_name = driver_portal.reply_to_ticket(
                issue_name,
                "Credential-attributed reply.",
            )["name"]
            self.assertEqual(frappe.session.user, "Guest")
            detail = driver_portal.get_ticket(issue_name)

        self.assertEqual(
            frappe.db.get_value("Issue", issue_name, "raised_by"),
            driver_user,
        )
        self.assertEqual(
            frappe.db.get_value(
                "Communication", communication_name, "sender"
            ),
            driver_user,
        )
        timeline = {
            row["name"]: row["sender"] for row in detail["communications"]
        }
        self.assertEqual(timeline[communication_name], driver_user)

    def test_attendance_photo_is_a_private_native_attachment_on_owned_record(self):
        parameters = inspect.signature(driver_portal.driver_check_in).parameters
        self.assertIn("photo_filename", parameters)
        token = self._driver_token()
        photo = _image_data_uri("PNG")
        frappe.set_user("Guest")
        with _request_cookies({"masar_dt": token._plaintext_token}):
            result = driver_portal.driver_check_in(
                photo=photo,
                photo_filename="attendance.png",
            )
        attachment = frappe.db.get_value(
            "File",
            {
                "attached_to_doctype": "Driver Attendance",
                "attached_to_name": result["name"],
            },
            ["is_private", "file_url"],
            as_dict=True,
        )
        self.assertTrue(attachment)
        self.assertTrue(attachment.is_private)
        self.assertEqual(
            frappe.db.get_value(
                "Driver Attendance Image",
                {"parent": result["name"]},
                "image",
            ),
            attachment.file_url,
        )

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

    def test_mixed_driver_binding_rejected_on_insert(self):
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

    def test_driver_party_type_without_worker_subject_is_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(
                {
                    "doctype": "Masar Worker Token",
                    "holder_type": "Driver",
                    "driver": self.driver,
                    "party_type": "Employee",
                }
            ).insert(ignore_permissions=True)

    def test_legacy_driver_default_is_normalized_without_touching_mixed_rows(self):
        legacy = self._driver_token()
        raw_token = legacy._plaintext_token
        frappe.db.set_value(
            "Masar Worker Token",
            legacy.name,
            "party_type",
            "Employee",
            update_modified=False,
        )
        self.assertIsNone(
            frappe.db.get_value("Masar Worker Token", legacy.name, "party")
        )

        mixed_driver = self._make_driver()
        mixed_employee = self._make_employee()
        mixed = self._driver_token(mixed_driver)
        frappe.db.set_value(
            "Masar Worker Token",
            mixed.name,
            {
                "party_type": "Employee",
                "party": mixed_employee,
                "employee": mixed_employee,
            },
            update_modified=False,
        )
        frappe.get_meta("Masar Worker Token").autoname = "hash"

        with self.assertRaises(frappe.PermissionError):
            resolve_driver_token(raw_token)
        with self.assertRaises(frappe.ValidationError):
            issue_driver_link(self.driver)

        legacy_binding = frappe.db.get_value(
            "Masar Worker Token",
            legacy.name,
            ["holder_type", "driver", "party_type", "party", "employee"],
            as_dict=True,
        )
        self.assertEqual(legacy_binding.holder_type, "Driver")
        self.assertEqual(legacy_binding.driver, self.driver)
        self.assertEqual(legacy_binding.party_type, "Employee")
        self.assertFalse(legacy_binding.party)
        self.assertFalse(legacy_binding.employee)

        from apex.patches.v2_0.normalize_legacy_driver_token_bindings import execute

        execute()
        execute()

        self.assertIsNone(
            frappe.db.get_value("Masar Worker Token", legacy.name, "party_type")
        )
        self.assertEqual(resolve_driver_token(raw_token), self.driver)
        reissued = issue_driver_link(self.driver)
        self.assertEqual(reissued["token"], raw_token)
        reissued_binding = frappe.db.get_value(
            "Masar Worker Token",
            legacy.name,
            ["party_type", "party", "employee"],
            as_dict=True,
        )
        self.assertFalse(reissued_binding.party_type)
        self.assertFalse(reissued_binding.party)
        self.assertFalse(reissued_binding.employee)
        self.assertEqual(resolve_driver_token(reissued["token"]), self.driver)

        mixed_binding = frappe.db.get_value(
            "Masar Worker Token",
            mixed.name,
            ["party_type", "party", "employee"],
            as_dict=True,
        )
        self.assertEqual(mixed_binding.party_type, "Employee")
        self.assertEqual(mixed_binding.party, mixed_employee)
        self.assertEqual(mixed_binding.employee, mixed_employee)

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
        doctype_path = (
            Path(__file__).resolve().parents[1]
            / "apex_core"
            / "doctype"
            / "masar_worker_token"
            / "masar_worker_token.json"
        )
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
        (the A-209 bug -- a pre-made key handed to ``delete_value`` is prefixed a
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

        # [#a110iso] The second address still answers with the ordinary 403 — the
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
        for status in ("Stopped", "On Leave", "Released"):
            with self.subTest(status=status):
                driver = frappe.get_doc("Salis Driver", self.driver)
                driver.status = "Active"
                driver.save(ignore_permissions=True)
                issued = issue_driver_link(self.driver)
                driver.status = status
                driver.save(ignore_permissions=True)

                self.assertEqual(
                    frappe.db.get_value(
                        "Masar Worker Token", {"driver": self.driver}, "enabled"
                    ),
                    0,
                )
                driver.status = "Active"
                driver.save(ignore_permissions=True)
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
        self.assertTrue(
            hasattr(token_security, "revoke_subject_tokens"),
            "central subject-token revocation helper is missing",
        )
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
        self.assertTrue(
            hasattr(token_security, "revoke_subject_tokens"),
            "central subject-token revocation helper is missing",
        )
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

                savepoint = f"stale_reenable_{audience.lower()}"
                frappe.db.savepoint(savepoint)
                try:
                    with self.assertRaises(frappe.PermissionError):
                        doc.db_set("enabled", 1)
                    self.assertEqual(
                        frappe.db.get_value("Masar Worker Token", name, "enabled"),
                        0,
                    )
                    with self.assertRaises(frappe.PermissionError):
                        resolve(issued["token"])
                finally:
                    frappe.db.rollback(save_point=savepoint)

    def test_stale_cached_db_set_cannot_install_partial_forged_credential(self):
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
                issue(subject)
                name = frappe.db.get_value(
                    "Masar Worker Token",
                    {"holder_type": audience, subject_field: subject},
                    "name",
                )
                doc = frappe.get_doc("Masar Worker Token", name)
                doc.load_doc_before_save()
                self.assertEqual(doc.get_doc_before_save().enabled, 1)
                token_security.revoke_subject_tokens(audience, subject)
                persisted = frappe.db.get_value(
                    "Masar Worker Token",
                    name,
                    ["enabled", "token", "token_enc"],
                    as_dict=True,
                )
                forged = frappe.generate_hash(length=48)

                savepoint = f"stale_forgery_{audience.lower()}"
                frappe.db.savepoint(savepoint)
                try:
                    with self.assertRaises(frappe.PermissionError):
                        doc.db_set(
                            {"enabled": 1, "token": _hash_token(forged)}
                        )
                    current = frappe.db.get_value(
                        "Masar Worker Token",
                        name,
                        ["enabled", "token", "token_enc"],
                        as_dict=True,
                    )
                    self.assertEqual(current, persisted)
                    with self.assertRaises(frappe.PermissionError):
                        resolve(forged)
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

        self.assertIn("Building", str(error.exception))

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

        self.assertIn("Project", str(error.exception))

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

    def test_scoped_driver_reshare_rotates_and_persists(self):
        project = self._make_project()
        driver = self._make_driver(project=project)
        first = issue_driver_link(driver)
        user = self._make_user(
            "Fleet Supervisor", allow="Project", for_value=project
        )

        with _as_user(user):
            second = issue_driver_link(driver)

        self.assertNotEqual(second["token"], first["token"])
        self.assertEqual(
            frappe.db.get_value(
                "Masar Worker Token", {"driver": driver}, "token"
            ),
            _hash_token(second["token"]),
        )
        with self.assertRaises(frappe.PermissionError):
            resolve_driver_token(first["token"])
        self.assertEqual(resolve_driver_token(second["token"]), driver)

    def test_fleet_supervisor_can_reissue_disabled_driver_with_rotation(self):
        project = self._make_project()
        driver = self._make_driver(project=project)
        first = issue_driver_link(driver)
        token_security.revoke_subject_tokens(token_security.DRIVER, driver)
        user = self._make_user(
            "Fleet Supervisor", allow="Project", for_value=project
        )

        with _as_user(user):
            second = issue_driver_link(driver)

        self.assertNotEqual(second["token"], first["token"])
        persisted = frappe.db.get_value(
            "Masar Worker Token",
            {"holder_type": "Driver", "driver": driver},
            ["enabled", "token"],
            as_dict=True,
        )
        self.assertEqual(persisted.enabled, 1)
        self.assertEqual(persisted.token, _hash_token(second["token"]))
        with self.assertRaises(frappe.PermissionError):
            resolve_driver_token(first["token"])
        self.assertEqual(resolve_driver_token(second["token"]), driver)

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
        doctype_path = (
            Path(__file__).resolve().parents[1]
            / "apex_core"
            / "doctype"
            / "masar_worker_token"
            / "masar_worker_token.json"
        )
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
