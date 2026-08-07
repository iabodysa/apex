# Housing Operations Track

## Audience

Run this as a multi-account track. Accommodation Managers, Resident
Supervisors, Resident Request Coordinators, Cleaning Supervisors, and
Maintenance Technicians complete only their role-owned checkpoints. A System
Manager provisions the draft Maintenance Work Order but is not a learner.

## Outcome

Trace a resident's housing journey from reusable masters through assignment,
custody, service requests, and checkout across controlled role handoffs.

## Prerequisites

- Separate training accounts for each participating housing role.
- Trainer-provided Site, Building, Room, Bed, resident, and item records.
- A safe draft Maintenance Work Order linked to a training Maintenance Request
  and provisioned by System Manager.
- Building User Permissions where the role is building-scoped.

## Learning path

1. [Frappe Foundations](../foundations.md)
2. [Accommodation](../accommodation.md)
3. [Contingent Workers](../contingent-workers.md) — optional for cohorts that
   receive passport-only arrivals before an Employee exists.
4. [Custody](../custody.md)
5. [Maintenance](../maintenance.md)
6. [Costs and Leasing](../costs.md)
7. **Role Permissions Manager** (`/app/permission-manager`)

## Practice checkpoint

On the training site, trace one demo resident through an available bed,
assignment, issued article, maintenance request, return, and checkout.

- Accommodation Manager or Resident Supervisor traces the housing and custody
  records that their account can read.
- Resident Request Coordinator records and triages the request, then hands it
  to the housing team.
- Cleaning Supervisor submits the assigned Cleaning Log checkpoint.
- The trainer signs in as System Manager, opens and verifies the prepared draft
  Maintenance Work Order, records its handoff, and signs out. Do not create a
  second Work Order. Never lend that account or add its role to a learner.
- Maintenance Technician updates only the exercise's actual dates, completion
  notes, and sanitized completion photo on that draft. The learner does not
  submit, cancel, add procurement cost, or change the source link.

Use each record's timeline to explain its owned Save or Submit action. Change
accounts at handoff; do not add roles to one learner account.

## Verification

The cohort can identify:

- which records are masters and which are transactions;
- the source record for occupancy, custody, and maintenance history;
- the next responsible role when the current account cannot submit or cancel;
- the Building scope applied to a supervisor.

Each role-specific participant can also complete its own checkpoint and name
the role responsible for the next action. The Maintenance Technician can show
the allowed draft changes and the absence of Submit and Cancel authority.

## Data safety

Use demo residents and assets only. Do not reassign an occupied production bed,
change a live holder, or cancel an official record for practice. Let the trainer
reverse or remove the training scenario through normal document actions.
