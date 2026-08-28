# Complete a Fleet Movement in Salis

[Back to the training index](README.md)

## Outcome

Prepare a recurring route, group approved transport requests into an executable trip,
follow boarding, and close the trip with traceable fulfilment evidence.

## Intended role

- A **Fleet Project Manager** or **Fleet Manager** maintains Work Shifts and Route
  Templates, creates recurring Route Assignments, and submits vehicle handovers.
- A **Fleet Supervisor** prepares operational records, validates and authorizes eligible
  requests, approves recurring Route Assignments, groups requests, and dispatches trips.
- A **Fleet Project Manager** or **Fleet Manager** completes a dispatched trip.
- A separate **Fleet Supervisor** may use **Authorize (Regional)** when the
  request stays below the Operations threshold. A **Fleet Manager** uses
  **Authorize (Operations)** when Salis derives that the higher tier is required.
- The user named as **Route Supervisor** follows operating assignments and trips within
  their scope in Masar Supervisor.

Do not add all of these roles to one learner. Change accounts at each handoff.

## Before starting

- Work on a non-production site with one training `Project` and the matching
  Project User Permissions.
- Prepare one Active `Salis Vehicle` with a seat capacity and current compliance,
  one Active `Salis Driver` linked to an Active employee who is not on approved
  leave, and two fictional workers for the passenger list.
- Prepare one active `Work Shift` with the correct days and times, and one active
  `Route Template` with ordered stops.
- Prepare separate maker, authorizer, dispatcher, route-supervisor, driver, and worker
  accounts.
- Use fictional signed evidence for the handover. Do not use a production plate,
  driver, worker, route, or attachment.

## End-to-end exercise

1. As the Fleet Supervisor, confirm the vehicle's Project, status, capacity,
   odometer, and compliance documents. Confirm the driver's Project, status,
   licence, and employee link.
2. Create an Active `Vehicle Assignment` for the vehicle and driver. A Fleet
   Project Manager or Fleet Manager submits it. Confirm that the vehicle's
   **Current Driver** and the driver's **Current Vehicle** match the submitted
   assignment.
3. Record physical custody in `Vehicle Handover`. Use the assigned driver as
   **To Driver**, complete the checklist, attach signed evidence, and submit it
   with an authorized account. If **Discrepancy** is selected, enter discrepancy
   notes and route the damage decision through `Vehicle Damage Write-Off`.
4. As the maker, create two `Transport Request` records of type **Site Transport**.
   Give them different pickup or drop-off stops and one fictional worker each. Use
   **Validate** on both.
5. Change to a different authorized account. Use **Authorize (Regional)** when
   **Needs Operations** is clear; otherwise a Fleet Manager uses **Authorize
   (Operations)**. Both requests are now `Approved`.
6. Create a `Route Assignment` from the prepared Work Shift and Route Template. Set the
   Project, default vehicle and driver, operating dates, and Route Supervisor. A Fleet
   Supervisor or Fleet Manager uses **Approve**. Submission generates planned
   `Dispatch Trip` records for the planning horizon without duplicating a date.
7. Open one planned Dispatch Trip. Confirm that it copied the ordered stops and default
   Project, vehicle, driver, and shift from the approved assignment.
8. Add both approved requests to the trip. Map each request to its pickup and drop-off
   stop. Confirm that the trip builds one passenger list without duplicating an Employee
   who appears in more than one request.
9. As the Route Supervisor, open **Masar Supervisor** and confirm the request queue,
   recurring assignment, trip, stops, driver, vehicle, and passenger count. As the Fleet
   Supervisor, use **Dispatch** only after the stops and request mappings are ready.
10. The driver runs the trip, records stops and boarding outcomes, and closes driver
    execution. Enter completion notes in the staff-owned Dispatch Trip. If odometer
    readings are used, enter both values and keep the end reading at or above the start.
    A Fleet Project Manager or Fleet Manager uses **Complete**.

The completed trip fulfils every linked request in one transaction, advances the vehicle
odometer when the new value is higher, and creates one `Trip Fulfilment Ledger` row.

## Decisions and exceptions

- Use **Site Transport** for accommodation-to-project movement,
  **Inter-City Relocation** for a move containing at least one worker, and
  **Administrative Trip** for a destination-only trip without a worker manifest.
- Salis derives worker count and the required authority tier. Do not try to lower
  **Needs Operations**, and never authorize a request you created or requested.
- `Work Shift` owns days and times. `Route Template` owns reusable ordered stops.
  `Route Assignment` combines them with Project, default driver, default vehicle, and
  approval. `Dispatch Trip` is the actual dated journey.
- One trip may contain several Transport Requests. Each request keeps its own pickup and
  drop-off mapping, so one trip can serve workers travelling to different stops.
- A one-off journey starts as an **Ad Hoc** Dispatch Trip and does not need a recurring
  Route Assignment, but it still needs stops, resources, and mapped requests or passengers.
- `Vehicle Assignment` is the authoritative pairing. `Vehicle Handover` records
  physical custody; when custody changes to another driver, create the matching
  assignment rather than relying on the handover mirror alone.
- Expired vehicle compliance warns or blocks assignment and dispatch according
  to `Salis Settings`. Resolve the compliance issue instead of changing a mirror
  field.
- Approving a recurring Route Assignment generates planned trips; it does not dispatch or
  complete them. Assigning an approved Transport Request to a trip moves it to
  `Scheduled`. Completing the trip fulfils all assigned requests together.
- The driver's portal completion records a `Trip Start Log`; it does not complete
  the `Dispatch Trip`. The Fleet Project Manager or Fleet Manager owns that final
  workflow action.
- Cancelling a completed trip is a Fleet Manager action. It returns the request
  to `Scheduled`, removes the fulfilment ledger row, and reverses boarding, but
  it deliberately does not reduce the vehicle odometer.

## Evidence of completion

- The submitted `Vehicle Assignment` and both fleet masters show the same pair.
- The submitted `Route Assignment` records `Approved`, the assigned supervisor, and the
  approval time, and its generated-through date advances without duplicate trips.
- Both `Transport Request` records are `Fulfilled` and link the same trip, vehicle, and
  driver while retaining their own stop mappings.
- The `Dispatch Trip` is submitted in `Completed` with completion notes.
- One `Trip Fulfilment Ledger` row points to the trip, and the vehicle odometer
  shows the completed reading.
- The learner can show that another Project is absent or denied under the scoped
  account.

## Related links

- [Fuel operations](fuel.md)
- [Masar, driver, and supervisor journeys](portals-masar-driver.md)
- [Fleet compliance and financial handoffs](compliance.md)
