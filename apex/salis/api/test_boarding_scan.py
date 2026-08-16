# Copyright (c) 2026, AFMCO and contributors
"""QR boarding-pass + scan-validate tests (Salis driver passenger-boarding).

Proves the end-to-end boarding flow on ``salis.api.boarding``:

  1. a Valid scan of an issued pass appends ONE Trip Boarding Event row to the
     trip's Trip Start Log AND writes a Boarding Scan Log audit row (result Valid,
     boarding_event_created set) — the core goal: a scan logs a row;
  2. a second scan of the same worker is a Duplicate — no second boarding row,
     but the duplicate attempt is still audited;
  3. a forged/tampered token is Invalid Token and creates no boarding row;
  4. a pass for a worker not on the trip's manifest is rejected at issue time, and
     a hand-built token for an off-manifest worker scans as Wrong Trip;
  5. the issued pass never leaks the raw token into the audit row (only its hash);
  6. the pass read's ceiling keys on the TRANSPORT PEER as well as the address, and a
     caller can no longer name its own bucket — see TestBoardingPassRateKey.

The trip fixture reuses the proven worker-trip builder from the Masar movement
tests; everything is created as Administrator with ignore_permissions, then the
scan endpoint is exercised directly.
"""

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    issue_driver_link,
)
from apex.apex_core.utils import portal_identity as token_security
from apex.salis.api import boarding
from apex.tests.factories import (
    WorkerTripMixin as _WorkerTripMixin,
    make_masar_building as _building,
    make_worker_employee as _employee,
    make_project as _project,
)


BAD_TOKEN_SUBNET = "2001:db8:5ca7::"


def _fresh_ip():
    """An address no other block in the app can be using: this file's own slice of
    the RFC 3849 documentation prefix, plus a random suffix.

    The portal bad-token window is keyed on the ADDRESS ALONE (one budget of
    ``BAD_TOKEN_ATTEMPTS_PER_MINUTE`` per IP, spent across every entry), so a
    shared ``127.0.0.1`` would let this file's failed cookies spend another test
    file's budget and turn somebody else's push red.
    """
    return BAD_TOKEN_SUBNET + frappe.generate_hash(length=12)


class _Request:
    def __init__(self, cookies, remote_addr):
        self.cookies = cookies
        self.remote_addr = remote_addr


@contextmanager
def _request_cookies(cookies):
    """One request surface per block, on its OWN address, leaving no window behind.

    The name handed to the cache on the way out is deliberately RAW:
    ``delete_value`` re-applies ``make_key`` (redis_wrapper.py:141-142), so an
    already-made key is prefixed a second time and clears nothing.
    """
    ip = _fresh_ip()
    sentinel = object()
    previous_request = getattr(frappe.local, "request", sentinel)
    previous_ip = getattr(frappe.local, "request_ip", sentinel)
    previous_form = getattr(frappe.local, "form_dict", sentinel)
    frappe.local.request = _Request(cookies, ip)
    frappe.local.request_ip = ip
    frappe.local.form_dict = frappe._dict(
        {"cmd": "boarding-scan-" + frappe.generate_hash(length=12)}
    )
    try:
        yield ip
    finally:
        frappe.cache.delete_value(token_security.BAD_TOKEN_WINDOW_KEY.format(ip))
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


class TestBoardingScan(_WorkerTripMixin, FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.project = _project("Boarding Scan Project")
        cls.building = _building("Boarding Scan Building")
        tag = frappe.generate_hash(length=12).upper()
        cls.driver = (
            frappe.get_doc(
                {
                    "doctype": "Salis Driver",
                    "full_name": f"Boarding Driver {tag}",
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        cls.other_driver = (
            frappe.get_doc(
                {
                    "doctype": "Salis Driver",
                    "full_name": f"Boarding Other Driver {tag}",
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        cls._token_meta = frappe.get_meta("Masar Worker Token")
        cls._original_token_autoname = cls._token_meta.autoname
        cls.addClassCleanup(
            setattr,
            cls._token_meta,
            "autoname",
            cls._original_token_autoname,
        )
        cls._token_meta.autoname = "hash"
        cls.driver_token = issue_driver_link(cls.driver)["token"]
        cls.other_driver_token = issue_driver_link(cls.other_driver)["token"]
        cls.w1 = _employee("Boarding Worker One")
        cls.w2 = _employee("Boarding Worker Two")
        cls.off_manifest = _employee("Boarding Off Manifest")

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for driver in (cls.driver, cls.other_driver):
            token_name = frappe.db.get_value(
                "Masar Worker Token",
                {"holder_type": "Driver", "driver": driver},
                "name",
            )
            if token_name:
                frappe.delete_doc(
                    "Masar Worker Token",
                    token_name,
                    ignore_permissions=True,
                    force=True,
                )
            if frappe.db.exists("Salis Driver", driver):
                frappe.delete_doc(
                    "Salis Driver",
                    driver,
                    ignore_permissions=True,
                    force=True,
                )
        if frappe.db.exists("Building", cls.building):
            frappe.delete_doc("Building", cls.building, ignore_permissions=True, force=True)
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _cleanup_logs(self, dispatch_trip):
        """Drop any Trip Start Log + Boarding Scan Log rows the scan created."""
        def _purge():
            frappe.set_user("Administrator")
            for name in frappe.get_all(
                "Boarding Scan Log",
                filters={"dispatch_trip": dispatch_trip},
                pluck="name",
            ):
                frappe.delete_doc("Boarding Scan Log", name, ignore_permissions=True, force=True)
            for name in frappe.get_all(
                "Trip Start Log",
                filters={"dispatch_trip": dispatch_trip},
                pluck="name",
            ):
                doc = frappe.get_doc("Trip Start Log", name)
                if doc.docstatus == 1:
                    try:
                        doc.cancel()
                    except Exception:
                        pass
                frappe.delete_doc("Trip Start Log", name, ignore_permissions=True, force=True)

        self.addCleanup(_purge)

    def _paired_trips(self, suffix):
        _tr, _rp, own_trip = self._worker_trip(
            self.driver,
            self.project,
            self.building,
            [self.w1],
            f"Credential Own {suffix}",
        )
        _other_tr, _other_rp, other_trip = self._worker_trip(
            self.other_driver,
            self.project,
            self.building,
            [self.w2],
            f"Credential Other {suffix}",
        )
        return own_trip, other_trip

    def _assert_guest_rejected_before_trip_read(self, dispatch_trip):
        frappe.set_user("Guest")
        real_get_value = boarding.frappe.db.get_value
        with _request_cookies({}), patch.object(
            boarding.frappe.db,
            "get_value",
            wraps=real_get_value,
        ) as reads:
            with self.assertRaises(frappe.PermissionError):
                boarding._resolve_trip(dispatch_trip)
        trip_reads = [
            call
            for call in reads.call_args_list
            if call.args and call.args[0] == "Dispatch Trip"
        ]
        self.assertEqual(trip_reads, [])

    def test_missing_guest_credential_is_denied_before_trip_lookup(self):
        """The pre-read Guest denial fires before ANY Dispatch Trip lookup,
        whether the named trip exists or is missing entirely."""
        own_trip, _other_trip = self._paired_trips(self._testMethodName)
        with self.subTest(trip="existing trip"):
            self._assert_guest_rejected_before_trip_read(own_trip.name)
        with self.subTest(trip="missing trip"):
            self._assert_guest_rejected_before_trip_read(
                "MISSING-" + frappe.generate_hash(length=12)
            )

    def test_staff_without_driver_credential_can_resolve_any_trip(self):
        _own_trip, other_trip = self._paired_trips(self._testMethodName)
        frappe.set_user("Administrator")
        with _request_cookies({}):
            resolved = boarding._resolve_trip(other_trip.name)
        self.assertEqual(resolved.name, other_trip.name)

    def test_staff_session_with_driver_cookie_can_resolve_token_driver_trip(self):
        own_trip, _other_trip = self._paired_trips(self._testMethodName)
        frappe.set_user("Administrator")
        with _request_cookies({"masar_dt": self.driver_token}):
            resolved = boarding._resolve_trip(own_trip.name)
        self.assertEqual(resolved.driver, self.driver)

    def test_staff_session_with_driver_cookie_is_confined_to_token_driver_trip(self):
        _own_trip, other_trip = self._paired_trips(self._testMethodName)
        frappe.set_user("Administrator")
        with _request_cookies({"masar_dt": self.driver_token}):
            with self.assertRaises(frappe.PermissionError):
                boarding._resolve_trip(other_trip.name)

    def test_valid_driver_credential_denies_foreign_and_missing_trips_uniformly(self):
        _own_trip, other_trip = self._paired_trips(self._testMethodName)
        missing_trip = "MISSING-" + frappe.generate_hash(length=12)
        denials = []
        frappe.set_user("Guest")
        with _request_cookies({"masar_dt": self.driver_token}):
            for trip_name in (other_trip.name, missing_trip):
                with self.subTest(trip_name=trip_name):
                    with self.assertRaises(frappe.PermissionError) as denial:
                        boarding._resolve_trip(trip_name)
                    denials.append(str(denial.exception))
        self.assertEqual(denials[0], denials[1])

    def test_bad_presented_cookie_under_staff_session_is_denied(self):
        """A garbage or blank driver cookie is denied under a staff session,
        for a trip that belongs to someone else."""
        _own_trip, other_trip = self._paired_trips(self._testMethodName)
        frappe.set_user("Administrator")
        with _request_cookies({"masar_dt": "invalid"}):
            with self.assertRaises(
                frappe.PermissionError, msg="a garbage cookie must be denied"
            ):
                boarding._resolve_trip(other_trip.name)
        with _request_cookies({"masar_dt": ""}):
            with self.assertRaises(
                frappe.PermissionError, msg="a blank cookie must be denied"
            ):
                boarding._resolve_trip(other_trip.name)

    def test_bad_cookie_is_denied_before_missing_trip_lookup(self):
        """A garbage or blank driver cookie is denied before the trip lookup
        even runs, for a trip that does not exist."""
        frappe.set_user("Administrator")
        with _request_cookies({"masar_dt": "invalid"}):
            with self.assertRaises(
                frappe.PermissionError, msg="a garbage cookie must be denied"
            ):
                boarding._resolve_trip("MISSING-" + frappe.generate_hash(length=12))
        with _request_cookies({"masar_dt": ""}):
            with self.assertRaises(
                frappe.PermissionError, msg="a blank cookie must be denied"
            ):
                boarding._resolve_trip("MISSING-" + frappe.generate_hash(length=12))

    def test_each_request_block_gets_a_private_bad_token_window(self):
        """Non-vacuous isolation: every block starts on an address whose window is
        EMPTY (so the counter reads 1, not 2), and leaves no window behind.

        A shared address would pool this file's six charged failures with another
        file's into one 10-per-minute budget, and the eleventh would answer 429
        where a test asserted PermissionError -- red on whoever pushed next.
        """
        addresses = []
        for _ in range(2):
            with _request_cookies({"masar_dt": "invalid"}) as ip:
                addresses.append(ip)
                name = token_security.BAD_TOKEN_WINDOW_KEY.format(ip)
                with self.assertRaises(frappe.PermissionError):
                    boarding._resolve_trip("MISSING-" + frappe.generate_hash(length=12))
                self.assertEqual(
                    int(frappe.cache.get(frappe.cache.make_key(name)) or 0),
                    1,
                    "a reused address would carry another block's failed attempts",
                )
            self.assertIsNone(
                frappe.cache.get(frappe.cache.make_key(name)),
                f"the throttle window {name} outlived its cleanup",
            )
        self.assertNotEqual(addresses[0], addresses[1])

    # `test_cookie_context_restores_previously_absent_request_state` is not defined
    # here: its body called only `_request_cookies`, this FILE's own fixture, never
    # any symbol from `apex.salis.api.boarding` -- a failure would report a harness
    # defect, not a boarding.py one. Its save/restore contract is already exercised,
    # implicitly, by every other test in this class.

    def test_bad_cookie_cannot_write_forged_pass_audit(self):
        """A garbage or blank cookie is refused before any Boarding Scan Log
        row is written for a forged pass."""
        before = frappe.db.count("Boarding Scan Log")
        with _request_cookies({"masar_dt": "invalid"}):
            with self.assertRaises(
                frappe.PermissionError,
                msg="a garbage cookie must be refused before any pass write",
            ):
                boarding.scan_boarding_pass("forged-pass")
        self.assertEqual(
            frappe.db.count("Boarding Scan Log"),
            before,
            "a refused garbage-cookie scan must not write an audit row",
        )

        before = frappe.db.count("Boarding Scan Log")
        with _request_cookies({"masar_dt": ""}):
            with self.assertRaises(
                frappe.PermissionError,
                msg="a blank cookie must be refused before any pass write",
            ):
                boarding.scan_boarding_pass("forged-pass")
        self.assertEqual(
            frappe.db.count("Boarding Scan Log"),
            before,
            "a refused blank-cookie scan must not write an audit row",
        )

    def test_missing_cookie_guest_cannot_write_forged_pass_audit(self):
        before = frappe.db.count("Boarding Scan Log")
        frappe.set_user("Guest")
        with _request_cookies({}):
            with self.assertRaises(frappe.PermissionError):
                boarding.scan_boarding_pass("forged-pass")
        self.assertEqual(frappe.db.count("Boarding Scan Log"), before)

    def test_valid_cookie_preserves_invalid_pass_audit(self):
        with _request_cookies({"masar_dt": self.driver_token}):
            result = boarding.scan_boarding_pass("forged-pass")
        self.addCleanup(
            frappe.delete_doc,
            "Boarding Scan Log",
            result["scan_log"],
            ignore_permissions=True,
            force=True,
        )
        self.assertEqual(result["result"], "Invalid Token")

    def test_valid_scan_creates_boarding_and_audit_rows(self):
        """The core goal: a valid scan appends one Trip Boarding Event row to the
        trip's Trip Start Log and writes a Valid Boarding Scan Log row."""
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1, self.w2], "Scan Route A"
        )
        self._cleanup_logs(dt.name)

        pass_data = boarding.get_boarding_pass(dt.name, self.w1)
        self.assertIn("pass_token", pass_data)
        self.assertEqual(pass_data["worker"], self.w1)

        res = boarding.scan_boarding_pass(
            pass_data["pass_token"], accommodation_building=self.building
        )
        self.assertEqual(res["result"], "Valid")

        log = frappe.get_doc("Trip Start Log", res["trip_start_log"])
        self.assertEqual(log.boarded_count, 1)
        self.assertEqual(len(log.boarding_events), 1)
        row = log.boarding_events[0]
        self.assertEqual(row.worker, self.w1)
        self.assertEqual(row.method, "QR")
        self.assertEqual(row.accommodation_building, self.building)

        scan = frappe.get_doc("Boarding Scan Log", res["scan_log"])
        self.assertEqual(scan.result, "Valid")
        self.assertEqual(scan.employee, self.w1)
        self.assertEqual(scan.dispatch_trip, dt.name)
        self.assertEqual(scan.trip_start_log, log.name)
        self.assertEqual(scan.boarding_event_created, 1)

    def test_duplicate_scan_logs_no_second_boarding_row(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "Scan Route B"
        )
        self._cleanup_logs(dt.name)
        pass_data = boarding.get_boarding_pass(dt.name, self.w1)

        first = boarding.scan_boarding_pass(pass_data["pass_token"])
        self.assertEqual(first["result"], "Valid")
        second = boarding.scan_boarding_pass(pass_data["pass_token"])
        self.assertEqual(second["result"], "Duplicate")

        log = frappe.get_doc("Trip Start Log", first["trip_start_log"])
        self.assertEqual(log.boarded_count, 1)

        rows = frappe.get_all(
            "Boarding Scan Log",
            filters={"dispatch_trip": dt.name, "employee": self.w1},
            fields=["result"],
        )
        results = sorted(r["result"] for r in rows)
        self.assertEqual(results, ["Duplicate", "Valid"])

    def test_forged_token_is_invalid_and_creates_no_boarding(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "Scan Route C"
        )
        self._cleanup_logs(dt.name)
        pass_data = boarding.get_boarding_pass(dt.name, self.w1)
        forged = pass_data["pass_token"][:-4] + "0000"

        res = boarding.scan_boarding_pass(forged)
        self.assertEqual(res["result"], "Invalid Token")

        logs = frappe.get_all("Trip Start Log", filters={"dispatch_trip": dt.name})
        self.assertEqual(logs, [])
        self.assertTrue(frappe.db.exists("Boarding Scan Log", res["scan_log"]))

    def test_pass_for_off_manifest_worker_rejected_at_issue(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "Scan Route D"
        )
        self._cleanup_logs(dt.name)
        with self.assertRaises(frappe.ValidationError):
            boarding.get_boarding_pass(dt.name, self.off_manifest)

    def test_off_manifest_token_scans_as_wrong_trip(self):
        """A token minted for an off-manifest worker (bypassing issue-time guard)
        is rejected at scan time as Wrong Trip and creates no boarding row."""
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "Scan Route E"
        )
        self._cleanup_logs(dt.name)
        token = boarding._issue_token(dt.name, self.off_manifest)
        res = boarding.scan_boarding_pass(token)
        self.assertEqual(res["result"], "Wrong Trip")
        logs = frappe.get_all("Trip Start Log", filters={"dispatch_trip": dt.name})
        self.assertEqual(logs, [])

    def test_audit_row_stores_hash_not_raw_token(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "Scan Route F"
        )
        self._cleanup_logs(dt.name)
        pass_data = boarding.get_boarding_pass(dt.name, self.w1)
        res = boarding.scan_boarding_pass(pass_data["pass_token"])
        scan = frappe.get_doc("Boarding Scan Log", res["scan_log"])
        self.assertNotEqual(scan.pass_token_hash, pass_data["pass_token"])
        self.assertEqual(len(scan.pass_token_hash), 64)


class TestBoardingPassRateKey(FrappeTestCase):
    """What the pass read's ceiling actually counts.

    The endpoint shipped ``@rate_limit(key="frappe.request.remote_addr", ...)``, which
    reads like the transport peer and is not: ``key`` is a form_dict LOOKUP,
    ``frappe.form_dict.get(key, "")`` (rate_limiter.py:143), so it named a request FIELD.
    Nobody sends a field by that name, the identity collapsed to ``<ip>:``
    (rate_limiter.py:147-148), and a caller who DID send one chose their own bucket --
    form_dict is built from the query string and body (app.py:302-314).

    These tests spend REAL windows and read the counters back, because a test that
    asserts the decorator's arguments proves only that the string is still typed. The
    trip does not exist, so every call is refused after the charge and before any write:
    what is under test is which bucket the request landed in, not what it returned.
    """

    def setUp(self):
        frappe.set_user("Administrator")

    def _count(self, name):
        """The live count in one window, by its RAW name; None if never opened."""
        raw = frappe.cache.get(frappe.cache.make_key(name))
        return None if raw is None else int(raw)

    def _forget(self, *names):
        """Drop windows on the way out, RAW: delete_value re-applies make_key
        (redis_wrapper.py:141-142), so an already-made key clears nothing."""
        self.addCleanup(lambda: [frappe.cache.delete_value(n) for n in names])

    def _refused_pass_read(self):
        """One charged call. The trip is absent, so the answer is always the throw."""
        with self.assertRaises(frappe.DoesNotExistError):
            boarding.get_boarding_pass(
                "NO-SUCH-TRIP-" + frappe.generate_hash(length=12), "NO-EMP"
            )

    def test_two_peers_behind_one_address_consume_separate_windows(self):
        """The proof the card asks for: change ONLY the peer, get a separate window.

        The address is held constant across both calls, so the split cannot be the
        address doing the work -- and the address window counting BOTH is what shows
        the two calls really were one address wearing two connections.
        """
        with _request_cookies({}) as ip:
            cmd = frappe.local.form_dict.cmd
            peer_a, peer_b = "192.0.2.11", "192.0.2.12"
            self._forget(
                f"rl:{cmd}:pass-peer:{peer_a}",
                f"rl:{cmd}:pass-peer:{peer_b}",
                f"rl:{cmd}:pass-address:{ip}",
            )

            for peer in (peer_a, peer_b):
                frappe.local.request.remote_addr = peer
                self._refused_pass_read()

            self.assertEqual(self._count(f"rl:{cmd}:pass-peer:{peer_a}"), 1)
            self.assertEqual(self._count(f"rl:{cmd}:pass-peer:{peer_b}"), 1)
            self.assertEqual(self._count(f"rl:{cmd}:pass-address:{ip}"), 2)

    def test_one_peer_spends_a_single_shared_window(self):
        """The other half: same peer twice is one window at two, not two windows."""
        with _request_cookies({}) as ip:
            cmd = frappe.local.form_dict.cmd
            peer = "192.0.2.13"
            self._forget(
                f"rl:{cmd}:pass-peer:{peer}", f"rl:{cmd}:pass-address:{ip}"
            )

            frappe.local.request.remote_addr = peer
            self._refused_pass_read()
            self._refused_pass_read()

            self.assertEqual(self._count(f"rl:{cmd}:pass-peer:{peer}"), 2)

    def test_the_peer_ceiling_refuses_the_call_that_passes_it(self):
        """A counter nobody enforces is a metric. The limit is patched, never the
        identity: the key under test is still derived by the shipped code path.

        The address ceiling is left at its shipped 120 and only three calls are made,
        so the 429 cannot be coming from it.
        """
        with _request_cookies({}) as ip, patch.object(boarding, "PASS_PEER_LIMIT", 2):
            cmd = frappe.local.form_dict.cmd
            peer = "192.0.2.14"
            self._forget(
                f"rl:{cmd}:pass-peer:{peer}", f"rl:{cmd}:pass-address:{ip}"
            )

            frappe.local.request.remote_addr = peer
            self._refused_pass_read()
            self._refused_pass_read()
            with self.assertRaises(frappe.RateLimitExceededError) as raised:
                boarding.get_boarding_pass("NO-SUCH-TRIP", "NO-EMP")

        self.assertEqual(getattr(raised.exception, "http_status_code", None), 429)
        self.assertLess(3, boarding.PASS_ADDRESS_LIMIT)

    def test_a_caller_supplied_field_no_longer_buys_its_own_window(self):
        """The bypass the shipped key opened, closed.

        Two calls differing ONLY in a form field named ``frappe.request.remote_addr``
        must land in ONE address window. Under the decorator each value produced the
        identity ``<ip>:<value>`` and therefore a private 120, so a query string was
        enough to leave the limit behind. Both the old bucket names are asserted
        ABSENT, which is what distinguishes this from the counter simply moving.
        """
        with _request_cookies({}) as ip:
            cmd = frappe.local.form_dict.cmd
            chosen = ("first", "second")
            self._forget(
                f"rl:{cmd}:pass-address:{ip}",
                *(f"rl:{cmd}:{ip}:{value}" for value in chosen),
            )

            for value in chosen:
                frappe.local.form_dict["frappe.request.remote_addr"] = value
                self._refused_pass_read()
                self.assertIsNone(self._count(f"rl:{cmd}:{ip}:{value}"))

            self.assertEqual(self._count(f"rl:{cmd}:pass-address:{ip}"), 2)

    def test_a_request_with_no_peer_declines_instead_of_pooling(self):
        """No peer means no bucket, not a bucket named after nothing.

        Charging one anyway would put every peerless caller in a single window, so any
        of them could 429 the rest -- the same call the scan limiter above it makes.
        The second half is what keeps the first honest: with a peer present the charge
        must happen, or an empty body would pass the decline assertion.
        """
        for peer, expected in ((None, ["pass-address"]), ("192.0.2.15", ["pass-address", "pass-peer"])):
            with self.subTest(peer=peer), _request_cookies({}):
                frappe.local.request.remote_addr = peer
                charged = []
                with patch.object(
                    boarding,
                    "charge_window",
                    side_effect=lambda name, window, limit: charged.append(name) or 1,
                ):
                    boarding._enforce_pass_read_rate_limit()
                # rl:<cmd>:<scope>:<identity> -- indexed from the FRONT because the
                # identity is an IPv6 address here and carries colons of its own.
                self.assertEqual([name.split(":")[2] for name in charged], expected)

