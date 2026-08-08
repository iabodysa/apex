# Complete a Fleet Movement in Salis

[Back to the training index](README.md)

## Outcome

Assign a vehicle to a driver, approve a project-scoped transport request, plan
the route, dispatch the trip, and close it with a traceable fulfilment record.

## Intended role

- A **Fleet Supervisor** prepares the operational records, validates requests,
  and dispatches planned trips.
- A **Fleet Project Manager** or **Fleet Manager** submits assignments, handovers,
  and route plans and can complete a dispatched trip.
- A separate **Fleet Supervisor** may use **Authorize (Regional)** when the
  request stays below the Operations threshold. A **Fleet Manager** uses
  **Authorize (Operations)** when Salis derives that the higher tier is required.
- The user named as **Route Supervisor** signs off only the submitted plans
  assigned to them.

Do not add all of these roles to one learner. Change accounts at each handoff.

## Before starting

- Work on a non-production site with one training `Project` and the matching
  Project User Permissions.
- Prepare one Active `Salis Vehicle` with a seat capacity and current compliance,
  one Active `Salis Driver` linked to an Active employee who is not on approved
  leave, and one fictional worker for the passenger list.
- Prepare separate maker, authorizer, movement, and route-supervisor accounts.
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
4. As the maker, create a `Transport Request` of type **Site Transport**. Enter
   the training Building and Project, pickup time, locations, and the fictional
   worker. Use **Validate**.
5. Change to a different authorized account. Use **Authorize (Regional)** when
   **Needs Operations** is clear; otherwise a Fleet Manager uses **Authorize
   (Operations)**. The request is now `Approved`.
6. Create a `Route Plan` linked to the request. Add the vehicle, driver, Project,
   assigned Route Supervisor, and ordered stops. A Fleet Project Manager or
   Fleet Manager submits it. Submission moves the request to `Scheduled`.
7. As the assigned Route Supervisor, open **Masar Supervisor**, review the
   driver, vehicle, and stops, then approve the plan. If the plan is wrong,
   reject it with a reason and return it to the planner; do not dispatch it.
8. Create a `Passenger Manifest` when a named boarding list is required. Do not
   enter the same Employee twice.
9. As the Fleet Supervisor, create the `Dispatch Trip` in `Planned`, link the
   route, vehicle, driver, and date, then use **Dispatch**.
10. After the driver has finished the training run, enter completion notes. If
    odometer readings are used, enter both values and keep the end reading at or
    above the start. A Fleet Project Manager or Fleet Manager uses **Complete**.

The completed trip fulfils the linked request, records the assigned vehicle and
driver, advances the vehicle odometer when the new value is higher, and creates
one `Trip Fulfilment Ledger` row.

## Decisions and exceptions

- Use **Site Transport** for accommodation-to-project movement,
  **Inter-City Relocation** for a move containing at least one worker, and
  **Administrative Trip** for a destination-only trip without a worker manifest.
- Salis derives worker count and the required authority tier. Do not try to lower
  **Needs Operations**, and never authorize a request you created or requested.
- `Vehicle Assignment` is the authoritative pairing. `Vehicle Handover` records
  physical custody; when custody changes to another driver, create the matching
  assignment rather than relying on the handover mirror alone.
- Expired vehicle compliance warns or blocks assignment and dispatch according
  to `Salis Settings`. Resolve the compliance issue instead of changing a mirror
  field.
- Route-supervisor approval is a separate operational sign-off. It does not
  advance the `Transport Request` or `Dispatch Trip`, and Salis does not block a
  dispatch merely because that sign-off is still Pending. Check it before
  dispatch.
- The driver's portal completion records a `Trip Start Log`; it does not complete
  the `Dispatch Trip`. The Fleet Project Manager or Fleet Manager owns that final
  workflow action.
- Cancelling a completed trip is a Fleet Manager action. It returns the request
  to `Scheduled`, removes the fulfilment ledger row, and reverses boarding, but
  it deliberately does not reduce the vehicle odometer.

## Evidence of completion

- The submitted `Vehicle Assignment` and both fleet masters show the same pair.
- The `Route Plan` is submitted and its supervisor decision is `Approved`, with
  the deciding user and time recorded.
- The `Transport Request` is `Fulfilled` and links the route, trip, vehicle, and
  driver.
- The `Dispatch Trip` is submitted in `Completed` with completion notes.
- One `Trip Fulfilment Ledger` row points to the trip, and the vehicle odometer
  shows the completed reading.
- The learner can show that another Project is absent or denied under the scoped
  account.

## Related links

- [Fuel operations](fuel.md)
- [Masar, driver, and supervisor journeys](portals-masar-driver.md)
- [Fleet compliance and financial handoffs](compliance.md)
- [Modules, workspaces, and routes](../reference/routes-workspaces.md)
