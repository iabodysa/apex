# Repair orders — over-decomposed tests

**Card:** A-565 · **Site:** `ci.localhost`

## The measurement this comes from

| metric | frappe | erpnext | hrms | apex |
|---|---|---|---|---|
| test methods | 1472 | 2134 | 511 | **3126** |
| DocTypes | 272 | 503 | 150 | **156** |
| tests per DocType | 5.4 | 4.2 | 3.4 | **20.0** |
| median test length | 12 | 29 | 27 | **10** |
| **assertions per test** | 2.67 | **3.19** | 2.87 | **2.36** |
| test lines as % of code | 23.7 | 34.0 | 40.3 | **62.5** |

Apex tests are the SHORTEST and the MOST numerous, and assert the LEAST each. That combination has
one cause: a test method per assertion instead of a test method per scenario. 1060 of 3192 methods
(33.2%) carry one assertion or none in three statements or fewer.

The target is ERPNext's density — about 3.2 assertions per test — reached by merging, never by
deleting coverage. Mutation sampling scored 4 killed / 1 survived (and the survivor was an
equivalent mutant), so what is asserted today is worth keeping. Every assertion that exists now
must still exist when you are done.

## The merge rule

Two or more test methods in the same class MAY become one when ALL of these hold:

- they build the SAME fixture — same objects, same user, same state;
- each asserts a different facet of ONE behaviour;
- their names differ only in which facet they name.

They MUST NOT be merged when:

- one proves an acceptance and another a refusal — those are two scenarios;
- they run as different users, or under different settings;
- one is a negative control for the other (a control that shares a method with the thing it
  controls proves nothing);
- merging would make a failure ambiguous about which facet broke.

## The safeguard that makes merging safe

**Every assertion in a merged test carries a message naming what it proves.**

```python
self.assertEqual(row["status"], "Open", "a new request opens in Open")
self.assertIsNone(row["closed_on"], "an open request has no close date")
```

Diagnosability is the only real argument for one-assertion-per-method. A message restores it, so
merging costs nothing a reader needs. A merged test with bare assertions is a REGRESSION — do not
ship one.

## Procedure, per file

```
1. Read the whole test class before changing a line
2. Run it and record the exact "Ran N tests ... OK" line — that is your baseline
3. Merge only the groups the rule above allows
4. Run again; the assertion COUNT must not fall, only the method count
5. Report both numbers: methods before/after, assertions before/after
```

Do not touch the module under test. If a merge exposes a defect, stop on that file, leave the
failing test with a `TODO(A-565)` comment naming what it proves, and report it.

## Domain A — habitat

| File | thin/total |
|---|---|
| `apex/habitat/report/test_reports.py::TestReports` | 16/17 |
| `apex/habitat/doctype/lease/test_lease_payment.py::TestARentPaymentWithoutAPayableIsRefused` | 10/11 |
| `apex/habitat/api/test_arrivals_card_scope.py::TestArrivalsCardScope` | 9/20 |
| `apex/habitat/api/test_safety_checklist.py::TestSafetyChecklist` | 8/24 |
| `apex/habitat/doctype/resident_request/test_resident_request.py::TestAccommodationResidentRequest` | 8/17 |
| `apex/habitat/doctype/resident_request/test_resident_request_coordinator_perms.py` | 8/10 |

## Domain B — apex_core and shared tests

| File | thin/total |
|---|---|
| `apex/apex_core/utils/test_portal_token_security.py::TestPortalTokenSecurity` | 11/52 |
| `apex/tests/test_internal_auditor_docperms.py::TestInternalAuditorDocPerms` | 9/10 |
| `apex/apex_core/utils/test_worker_party.py::TestSyncPartyEmployee` | 6/8 |
| `apex/apex_core/utils/test_email_gate_recipients.py` | 6/7 |
| `apex/apex_core/doctype/apex_settings/test_apex_settings_rearch.py::TestRetentionSetting` | 6/6 |
| `apex/tests/test_report_scope.py::TestReportScopeLogic` | 5/8 |

## Domain C — salis

| File | thin/total |
|---|---|
| `apex/salis/utils/test_get_driver_for_user.py::TestGetDriverForUser` | 11/20 |
| `apex/salis/api/test_boarding_scan.py::TestBoardingScan` | 9/22 |
| `apex/salis/doctype/dispatch_trip/test_dispatch_trip.py::TestDispatchTripAggregate` | 9/16 |
| `apex/salis/api/test_masar_route_maps.py::TestMasarRouteMaps` | 8/13 |
| `apex/salis/doctype/trip_start_log/test_trip_start_log.py::TestTripStartLogOwnership` | 6/7 |

## Left alone, with the reason

- **`test_records.json` — all 92 stay.** Owner decision: they are necessary. The eight the runner
  never reaches are kept anyway.
- **`apex/apex_core/doctype/apex_stock_settings/test_apex_stock_settings.py` (15/16)** — the highest
  ratio on the board and deliberately skipped: another agent wrote it today, so merging it now would
  collide.
- **`apex/salis/api/driver_portal/test_images.py` (9/13)** — same reason.
