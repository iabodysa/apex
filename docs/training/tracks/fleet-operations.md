# Fleet Operations Track

## Audience

Fleet Managers, Fleet Project Managers, and Fleet Supervisors complete the
operational path. Finance Managers join the finance segment only. Run the
complete scenario as a multi-account cohort; finance accounts must not be used
to perform fleet operations.

## Outcome

Trace project-scoped fleet work from masters and assignment through dispatch,
fuel, rentals, and finance review.

## Prerequisites

- A training account with the intended fleet or finance role.
- Trainer-provided Project, vehicle, driver, and rental master data.
- Project User Permissions for scoped roles.

## Learning path

1. [Frappe Foundations](../foundations.md)
2. [Fleet and Movement](../fleet-movement.md)
3. [Fuel](../fuel.md)
4. [Rentals](../rentals.md)
5. [Payments and Approvals](../compliance.md)
6. [Driver and Worker Portals](../portals-masar-driver.md)
7. [Fleet permissions and project scope](../../reference/permissions.md#fleet-master-permissions)

## Practice checkpoint

Use one training Project to trace:

- vehicle assignment to a driver;
- a transport request into dispatch;
- a fuel request into movement and finance review;
- a rental movement into settlement.

Fleet learners perform the assignment, transport, dispatch, fuel, and rental
steps allowed by their role. The Finance Manager reviews only the payment,
settlement, and cost records available to that account. The trainer presents
source operational records when finance has no direct read permission.

Change accounts at each handoff instead of adding roles to one learner.

## Verification

Fleet learners can identify the Project scope on each operational transaction
and the next workflow owner. The Finance Manager can identify the source
reference exposed by the finance record without claiming access to dispatch or
transport records. Every learner can explain where maker-checker separation
applies.

## Data safety

Use demo vehicles, drivers, and Projects. Never change live compliance dates,
assignments, fuel balances, payment requests, or settlements for practice.
Keep the creator and reviewer accounts separate.
