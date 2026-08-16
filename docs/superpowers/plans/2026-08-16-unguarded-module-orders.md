# Repair orders — modules no test reaches

**Card:** A-564 · **Site:** `ci.localhost` · **Run:** `bench --site ci.localhost run-tests --module <dotted.path>`

47 modules carry real callables that no test reaches. Three domains below, disjoint by path. Each
order names the file, the callables, and the assertion the new test must make.

## Global constraints

- Write the failing test FIRST, run it, watch it fail, then make it pass.
- Test file sits beside the module: `<dir>/test_<stem>.py`.
- Subclass `frappe.tests.utils.FrappeTestCase`; it wraps each test in a transaction.
- Build fixtures with `apex.tests.factories`; never hard-code a generated name
  (`DRV-000023`, `HR-EMP-00893`) — those are read off a developer database and exist on no other site.
- A test record referenced by name must be one another `test_records.json` creates.
- No Arabic in code, comments or identifiers.
- Docstring on every module, class and test method. No `#` comments except a `TODO(A-564)`.
- Do not edit the module under test unless a test proves a defect; report the defect instead.

---

## Domain 1 — `apex/habitat/utils/**`

| Order | File | Callables | Assert |
|---|---|---|---|
| 1.1 | `room_generator.py` | 17 | generating rooms for a building twice creates none the second time; a bed count matches the room's `bed_capacity`; a `Basement` floor type is placed below ground |
| 1.2 | `safety_setup.py` | 10 | seeding a safety catalogue twice creates one row per task code; a re-run keyed on `safety_task_catalog` adds nothing |
| 1.3 | `building_rollup.py` | 5 | the rollup counts only live occupancy; a cancelled assignment is excluded |
| 1.4 | `arrival_slips.py` | 4 | a slip for `party_type == "Employee"` renders the employee's name; a Temporary Worker slip renders the passport number |

Run after each: `bench --site ci.localhost run-tests --module apex.habitat.utils.test_<stem>`

## Domain 2 — `apex/salis/api/**`

| Order | File | Callables | Assert |
|---|---|---|---|
| 2.1 | `operations_alerts.py` | 15 | each alert fires only when its threshold is crossed; no alert fires on an empty site |
| 2.2 | `assignment_queue.py` | 5 | the queue lists only unassigned rows in the caller's project scope |
| 2.3 | `driver_portal/images.py` | 3 | a non-image upload is refused; an oversized file is refused |
| 2.4 | `maps_links.py` | 2 | a link is built from stored coordinates and omits nothing the map needs |

Run after each: `bench --site ci.localhost run-tests --module apex.salis.api.test_<stem>`

## Domain 3 — reports and `www`

| Order | File | Callables | Assert |
|---|---|---|---|
| 3.1 | `salis/report/vehicle_handover_register/*.py` | 3 | columns and row fieldnames agree; the scope guard returns `[]` for an out-of-scope caller |
| 3.2 | `salis/report/passenger_manifest_register/*.py` | 3 | same contract |
| 3.3 | `habitat/report/goods_receipt_register/*.py` | 3 | same contract |
| 3.4 | `habitat/report/room_bed_transfer_register/*.py` | 3 | same contract |
| 3.5 | `habitat/report/safety_incident_register/*.py` | 3 | same contract |
| 3.6 | `www/masar_supervisor.py` | 2 | the page context carries the keys the template reads |

Run after each: `bench --site ci.localhost run-tests --module <dotted.path.to.test_module>`

---

## Not ordered, and why

- **`apex/patches/v2_3/**`, `apex/patches/v2_6/**` (8 modules)** — a patch runs once per site and is
  retired afterwards. Three already carry a colocated test; the rest are one-shot migrations whose
  proof is the migrated site, not a unit test.
- **`apex/apex_core/setup/seeders/**` (4 modules)** — covered by A-563, which moves the largest of
  them onto exported customizations. Testing a module that is about to be deleted is waste.
- **`apex/tests/before_tests.py`** — the runner's own entry point; it runs on every suite invocation.
