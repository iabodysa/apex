# Follow Work from Request to Proof

[Back to training](README.md)

## Business outcome

Understand how Apex keeps an operational issue traceable from the first report to the
completed work, without treating each screen as an unrelated task.

## Journey and roles

Use a fictional air-conditioning fault in a resident room:

```text
Resident Request
  -> Maintenance Request
  -> Maintenance Work Order
  -> completion evidence and closed request
```

- A **Resident Request Coordinator** reviews the resident report and creates the linked
  maintenance request.
- A **System Manager** plans and submits the work order under the shipped permissions.
- A **Maintenance Technician** starts and completes the assigned work.

This foundation exercise traces an already completed training journey. The full operating
exercise is in [Maintenance Operations](maintenance.md).

## Before starting

The trainer prepares one fictional journey on a non-production site. It must contain no
personal data, real room details, signatures, QR codes, or confidential attachments.

The learner receives read access to the journey's Building and no access to a second
Building used for the scope check.

## Trace the journey

1. Open the prepared `Resident Request`. Identify its Building, Room, category, priority,
   description, and current state.
2. Open its target `Maintenance Request`. Confirm that the location and reported fault came
   from the resident request rather than being re-entered as a separate incident.
3. Open the linked `Maintenance Work Order`. Identify the planned assignee, planned dates,
   actual start and end dates, completion notes, and approved completion image.
4. Read the timeline and name the user and role responsible for each handoff.
5. Confirm the final operating result: the work order is **Completed** and the maintenance
   request is **Closed**.
6. Return to the resident request and confirm that its target link still leads to the same
   maintenance record.
7. Try the trainer's out-of-scope record. It must remain unavailable to the learner.

Do not edit a completed journey, generated cost record, or historical evidence during this
exercise.

## Expected state and evidence

The learner can show:

- one resident report linked to one maintenance request;
- one completed work order linked to that maintenance request;
- matching Building, Room, and fault details across the journey;
- actual work dates, completion notes, and a sanitized completion image;
- a closed maintenance request and an intact timeline; and
- denied access to the out-of-scope Building.

The business result is a resolved facility fault with clear ownership and proof, not three
disconnected records.

## Apply the same pattern

Other Apex journeys use the same source-to-outcome structure:

- `Transport Request` -> `Dispatch Trip` for one-off movement.
- `Work Shift` + `Route Template` -> approved `Route Assignment` -> generated
  `Dispatch Trip` for recurring movement.
- `Telecom Contract` -> `SIM Card` -> `SIM Custody Assignment` for contract-backed custody.

Use the domain guide for the actual decisions, states, and exceptions in each journey.

## Continue learning

- [Start a shift with assigned work](lessons/getting-started.md)
- [Approve a controlled request](lessons/records-and-workflows.md)
- [Prioritize the resident request queue](lessons/search-filter-export.md)
- [Choose a role track](README.md#role-tracks)
