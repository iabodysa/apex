# Contingent Workers in Logistay

[Back to training](README.md)

## Outcome

Record a passport-only arrival without inventing an Employee, record a paid
contractor without putting that person into housing, and complete the correct
housing, HR, or Finance handoff for each case.

## Intended role

- An **Accommodation Manager** or **Resident Supervisor** registers and houses a
  Temporary Worker from **Arrivals Desk**. Resident Supervisors are limited by
  Building User Permission; Accommodation Managers have building-wide oversight.
- An authorized **HR** user creates the permanent HRMS Employee when the worker's
  employment record is ready. Housing users do not create that Employee.
- A **Finance Manager** creates and maintains Freelancers, including the
  protected National ID/Iqama and monthly salary, and owns the native payment
  handoff.
- A **System Manager** is the administrative fallback. An Internal Auditor can
  review the records allowed by its field permissions.

Creating a Freelancer requires Finance Manager or System Manager access because
its required identity and salary fields are protected at permission level 1.

## Before starting

- Use a disposable training site and fictional passport, Iqama, phone, and
  salary values. Do not capture identity fields in screenshots or exports.
- For the arrival case, prepare a Building, Room, available Bed, Project, and an
  Accommodation Manager account or a Resident Supervisor account with Building
  access. An Arrival Batch and Labour Supplier are optional.
- If custody will be demonstrated, prepare a Custody Article and use an account
  that can submit Custody Issue. A Resident Supervisor can prepare the record but
  cannot submit it; an Accommodation Manager or System Manager owns that step.
- For the HR handoff, prepare an authorized HR account that can later create an
  active Employee with the same passport number.
- For the contractor case, prepare a Finance Manager account, a Project, an
  optional supervisor User, and the native accounting defaults required for a
  draft Payment Entry.

## Realistic end-to-end exercise

### Passport-only arrival

1. Open **Housing and Safety > Arrivals Desk** (`/app/arrivals-desk`). Search for
   the fictional passport first so an existing worker is not duplicated.
2. Register a **Temporary Worker** with the worker name, passport, Building, and
   Project. Review any scanned passport values before saving. Confirm the default
   30-day window and computed Expiry Date.
3. Select the worker, the demo Bed, and the Project, then complete check-in.
   Open the submitted **Housing Assignment** and confirm that Resident Type is
   Temporary Worker and that the Dynamic Link points to the new record.
4. In the Arrivals Desk completion panel, confirm that custody is marked
   **Custody deferred**, personal access is marked **Link after registration**,
   and transport is marked **Unregistered manifest**.
5. If property must be issued before the HR link, hand the worker to an authorized
   operator using **Custody Kiosk** with Party Type **Temporary Worker**. Arrivals
   Desk itself does not issue custody to this holder type.
6. Hand transport details to the authorized Fleet role. The Temporary Worker is
   entered in the Transport Request's **Additional (Unregistered) Passengers**
   table; the housing operator does not add the person to the Employee manifest.
7. When HR creates an active HRMS Employee with the same passport number, allow
   the daily link to complete. Confirm that the Temporary Worker becomes
   **Linked**, records the Linked Employee, and that supported housing and custody
   references now point to the Employee. Any skipped accommodation-cost rows for
   the active stay are backdated by that handoff.
8. Issue personal worker access only after the Employee link exists.

### Paid contractor

9. Sign in as Finance Manager and open **Freelancer List** from search. Create a
   fictional **Freelancer** with a unique National ID/Iqama, contract start and
   end dates, a positive Monthly Salary, and the applicable Project and
   supervisor.
10. Start a native **Payment Entry** under the approved Finance process, select
    Party Type **Freelancer**, and select the training record. Keep it in Draft
    unless the trainer has authorized a full non-production accounting exercise.
11. Confirm that saving the Freelancer created no Employee, Housing Assignment,
    payroll transaction, portal access, or automatic monthly payment.

## Decisions and exceptions

- Use **Temporary Worker** for a person who has arrived on a passport and needs a
  temporary housing or custody identity before an Employee exists. Passport is
  unique and cannot be changed after the first save. The window defaults to 30
  days and cannot exceed 90.
- Use the native **Employee** only after HR owns the permanent employment record.
  The daily passport match is the supported Temporary Worker-to-Employee
  handoff; do not relink records in the database.
- Use **Freelancer** for a fixed-monthly-salary contractor who is a payable party.
  The contract end date must be after the start date and salary must be positive.
  Finance uses the native ERPNext Payment Entry process; Apex does not generate a
  payment or payroll run.
- Temporary Worker, Employee, and Freelancer are not three statuses of one
  record. A Freelancer does not convert to either worker type, and it does not
  receive housing, custody, transport, payroll, or portal access automatically.
- If no matching Employee exists when a Temporary Worker's window lapses, the
  daily process marks it Expired and notifies HR. Housing an expired record gives
  a warning; it does not extend the window.
- A departure Transport Request from Housing Checkout requires a linked Employee.
  Complete the HR handoff before using that departure action.

## Evidence of completion

The housing learner can show:

- an Active Temporary Worker with a fictional passport, 30-day window, Expiry
  Date, Building, and Project;
- a submitted Housing Assignment linked by Resident Type and party to that
  Temporary Worker;
- the deferred-custody, personal-access, and unregistered-transport boundaries;
  and
- after the scheduled HR handoff, the Linked status, Linked Employee, and updated
  housing or custody reference.

The finance learner can show:

- one Freelancer with protected identity and salary values, valid contract dates,
  and the applicable Project and supervisor;
- a native draft Payment Entry that can select Party Type Freelancer and the
  training record; and
- the absence of automatically created Employee, housing, payroll, portal, and
  payment records.

## Related links

- [Accommodation](accommodation.md)
- [Custody](custody.md)
- [Worker and Driver Portals](portals-masar-driver.md)
