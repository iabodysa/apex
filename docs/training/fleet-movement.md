# Fleet and Movement

[Back to the training index](README.md)

## Audience

Fleet desk operators who maintain vehicles and drivers, assign custody, approve
transport, plan routes, and dispatch trips.

## Outcome

Complete one project-scoped movement from request to fulfilment while preserving
the source record, workflow state, vehicle assignment, and generated audit
records.

## Prerequisites

- Use a non-production site and a dedicated training `Project`.
- Prepare one active `Salis Vehicle`, one active `Salis Driver`, and two user
  accounts so the requester and authorizer are different people.
- Grant the trainee only the role and Project User Permission needed for the
  exercise. See [Fleet permissions](../reference/permissions.md#fleet-master-permissions).
- Review the shipped Desk and portal entry points in
  [Modules, Workspaces, and Routes](../reference/routes-workspaces.md).

## Native records and controls

Apex uses standard Frappe forms, Submit/Cancel, Workflows, attachments, timeline
comments, and Version history around these records:

- `Salis Vehicle` and `Salis Driver` are the fleet masters.
- `Vehicle Assignment` is the authoritative submitted vehicle-to-driver
  pairing. The current vehicle and driver fields on the masters are mirrors.
- `Vehicle Handover` records the custody checklist and signed evidence. It does
  not replace `Vehicle Assignment`.
- `Transport Request` owns demand and its approval workflow.
- `Route Plan` and `Passenger Manifest` hold the planned stops and passengers.
- `Dispatch Trip` owns execution and its workflow.
- `Trip Fulfilment Ledger` is generated when a trip completes. Operators do not
  create or edit it.

## Operational flow

### Maintain and assign the fleet

1. Set the vehicle plate, category, Project, status, ownership, seat capacity,
   and compliance documents on `Salis Vehicle`.
2. Link `Salis Driver` to the employee and set the Project, licence details, and
   status.
3. Submit `Vehicle Assignment` with the vehicle, driver, Project, and start
   date. The controller blocks overlapping active assignments and drivers who
   are stopped, released, inactive, or on approved leave.
4. Use `Vehicle Handover` when physical custody changes. Signed evidence is
   required before submit, and discrepancy notes are required when a
   discrepancy is recorded.

Expired vehicle compliance can warn or block assignment and dispatch according
to `Salis Settings`. Do not bypass that decision by editing the master mirrors.

### Approve a transport request

Choose the transport type that matches the work:

- Site Transport requires a Building and Project.
- Inter-City Relocation requires at least one worker.
- Administrative Trip requires a destination and cannot carry a worker
  manifest.

The `Transport Request Workflow` follows:

`New` → `Validated` → `Approved` → `Scheduled` → `Fulfilled`

A request can also be rejected, reopened, or cancelled through the available
workflow action. The system derives worker count and authority tier; a client
cannot lower the required approval. The requester cannot authorize their own
request.

### Plan and execute the trip

1. Create a `Route Plan` from the approved request, add ordered stops, vehicle,
   driver, and Project, then submit it. Submission moves the linked request to
   `Scheduled`.
2. Add a `Passenger Manifest` when a named passenger list is required. Duplicate
   employees are rejected.
3. Create `Dispatch Trip` in `Planned`, link the route, vehicle, driver, and trip
   date, then use the workflow:

   `Planned` → `Dispatched` → `Completed`

4. Enter completion notes. If odometer values are used, enter both start and end
   and keep the end value at or above the start value.
5. Completing the trip submits it, advances the vehicle odometer, moves the
   request to `Fulfilled`, and writes one `Trip Fulfilment Ledger` row.

Use `Fleet Control` for the scoped vehicle view and `Salis Dispatch Board` for
today's vehicles, drivers, trips, and open requests. Use `Worker Transport Plan`
before dispatch and `Transport Fulfilment SLA` after fulfilment.

Automation that checks idle vehicles, attendance, utilisation, and boarding is
listed in the [Scheduled Automation Reference](../reference/automation.md).

## Non-production exercise

1. Create training vehicle and driver masters under the training Project.
2. Submit a `Vehicle Assignment`.
3. Create an Administrative Trip `Transport Request` with a future pickup time,
   destination, and the training Project.
4. Use the requester account to validate it and a different authorized account
   to approve it.
5. Submit a one-stop `Route Plan` linked to the request.
6. Create a `Dispatch Trip`, dispatch it, then complete it with notes and a small
   valid odometer increase.

Do not add real employees to the manifest and do not use a production vehicle,
driver, Project, or route.

## Verification

- The assignment is submitted and both fleet masters show the same pairing.
- The request ends in `Fulfilled` and links the route, vehicle, driver, and trip.
- The trip is submitted in `Completed`.
- The vehicle odometer reflects the completed trip.
- Exactly one generated `Trip Fulfilment Ledger` row points to the trip.
- The Project-filtered board and reports do not expose another Project.

## Cleanup and data safety

Cancel records through their native lifecycle in reverse order:

1. Cancel the completed `Dispatch Trip`; the request returns to `Scheduled` and
   the system removes or reverses its generated trip effects.
2. Cancel the `Route Plan`; the request returns to `Approved`.
3. Cancel the `Transport Request` through its workflow.
4. Cancel the `Vehicle Assignment`.
5. Delete only unused training drafts and masters that have no remaining links.

Never edit generated ledgers, change `docstatus` directly, or delete submitted
production records.
