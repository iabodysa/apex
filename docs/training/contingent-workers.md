# Contingent Workers

[Back to training](README.md)

## Audience

Accommodation Managers and Resident Supervisors who receive Temporary Workers,
plus Finance Managers who create and maintain Freelancers. HR staff own the
native Employee handoff but have no Apex DocPerm on these two records unless
another role is also assigned. System Manager is an administrative fallback,
not the routine finance learner.

## Outcome

Choose the correct record for a passport-only arrival or an accounting
Freelancer, then complete only the branch owned by the learner's role.

## Prerequisites

- A non-production training site.
- For the housing branch: a trainer-provided Project, Building, Bed, optional
  Arrival Batch, and an Accommodation Manager or Resident Supervisor account.
- For the finance branch: a trainer-provided Project and Finance Manager
  account.
- Separate housing and finance accounts when both branches are taught, plus an
  HR handoff account only when the native Employee link is rehearsed.
- An authorized Fleet handoff account only when the trainer demonstrates the
  unregistered-rider transport step; otherwise no Fleet fixture is required.
- Contingent worker rights: filter **Role Permissions Manager** (`/app/permission-manager`) by Temporary Worker and Arrival Batch.

## Navigation by role

- **Housing branch:** an Accommodation Manager or Resident Supervisor opens
  **Arrivals Desk**, then uses Temporary Worker and the party-aware housing
  forms.
- **Finance branch:** a Finance Manager uses the Awesome Bar to open
  **Freelancer List**, then selects New.

Do not combine the branches in one learner account unless that learner actually
holds an appropriate role for both and the trainer assigned both checkpoints.
In a multi-account cohort, compare the housing-to-HR handoff with the separate
finance record; do not treat Temporary Worker and Freelancer as successive
states of one person.

## Choose the correct identity

### Temporary Worker

Use **Temporary Worker** for a person who has arrived with a passport but does
not yet have a permanent Employee record. It is a temporary housing and custody
identity, not a payroll or payable party.

The record requires a unique passport number and arrival date. Its stay window
defaults to thirty days, cannot exceed ninety days, and calculates an expiry
date. Its lifecycle is Active, Linked, or Expired.

### Employee

Use the native HRMS **Employee** after HR completes the permanent worker record.
The daily linking process matches an active Employee to an active Temporary
Worker by passport number.

### Freelancer

Use **Freelancer** for a short-term contractor paid as an accounting party. It
stores the identity, contract dates, positive monthly salary, Project, and
supervisor. The app registers Freelancer as an ERPNext payable Party Type, so
finance can use native accounting documents that support that party.

Freelancer is not a replacement for Temporary Worker or Employee. It does not
automatically receive housing, custody, transport, payroll, or portal access,
and no automatic monthly payment is created.

## Temporary Worker path

1. Open **Arrivals Desk** and search the expected arrivals or existing workers.
2. If no Employee exists, register a Temporary Worker from the passport
   details. Optional passport scanning only pre-fills fields; the operator must
   verify them.
3. Assign the Temporary Worker to an available bed through the party-aware
   housing flow.
4. Use the party-aware custody process if property must be issued. The Arrivals
   Desk completion pack deliberately defers custody and personal portal access
   for this holder type.
5. Arrivals Desk identifies the unregistered-manifest boundary. The housing
   learner hands the transport need to an authorized Fleet role, which may add
   the person as an unregistered rider. The housing learner does not create a
   Transport Request.
6. HR creates the active Employee with the same passport number.
7. The daily task links the records, repoints supported housing and custody
   references to the Employee, backdates skipped accommodation-cost rows, and
   marks the Temporary Worker Linked.
8. Issue personal worker access only after the Employee link exists.

If the window expires before a match, the task marks the Temporary Worker
Expired and sends an in-app notice to HR recipients. Housing an expired record
raises a warning; it does not silently extend the window.

Departure transport raised from Housing Checkout also requires a linked
Employee. Complete the link before that step.

## Freelancer path

1. The Finance Manager confirms that the person is an accounting contractor
   rather than a passport-only housing arrival.
2. Create the Freelancer with a unique national ID or Iqama, contract start and
   end dates, and positive monthly salary.
3. Add the Project and supervisor when they apply.
4. Let finance use the native ERPNext accounting process approved for the site.
5. Review the contract end date. Saving a record past that date derives Expired;
   use Terminated only for an intentional early end.

There is no automatic conversion between Freelancer, Temporary Worker, and
Employee.

## Exercise

Each learner completes only the branch owned by that account.

### Housing branch

1. Sign in as Accommodation Manager or Resident Supervisor and open
   **Arrivals Desk**.
2. Register a fictional `TRAINING` Temporary Worker with today's arrival date
   and the default window.
3. Assign the worker to a demo bed and confirm the Housing Assignment identifies
   the Temporary Worker party.
4. Confirm that personal worker access is unavailable, identify the
   unregistered-rider transport boundary, and record the handoff to the
   authorized Fleet role. Do not create a Transport Request.
5. Identify HR as the next role when a permanent Employee must be created and
   linked.

### Finance branch

1. Sign in as Finance Manager.
2. Use the Awesome Bar to open **Freelancer List**, select New, and create a
   fictional `TRAINING` Freelancer with a future contract end date and positive
   monthly salary.
3. Confirm the Project and supervisor when applicable.
4. Explain why the Freelancer does not create housing, payroll, or portal
   access.

Do not create a matching Employee during this exercise unless the trainer
intends to test the daily link and its record-repointing effects.

## Verification

The housing learner can show the Arrivals Desk record, housing assignment,
portal restriction, unregistered-transport boundary, Fleet handoff, and HR
handoff without creating a Transport Request.

The finance learner can show the Freelancer created from its List, its Project
and contract dates, and the absence of automatic housing, payroll, or portal
records.

When both branches run as a multi-account cohort, the learners compare their
separate records and explain why Temporary Worker, Employee, and Freelancer
must not be merged.

## Cleanup and data safety

Use fictional identity values only. End the demo housing assignment through the
supported checkout or cancellation path before removing training records.
Delete an unused Freelancer only when no native accounting document references
it. Never force a passport match, edit linked records in the database, or run
the daily linker on production for practice.
