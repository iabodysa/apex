# Maintenance Operations

[Back to training index](README.md)

## Outcome

Turn a reported facility fault into a planned work order, record the technician's work,
and close the request with completion evidence.

## Intended role

Any signed-in user may raise their own `Maintenance Request`. An
**Accommodation Manager**, **Resident Supervisor**, or
**Resident Request Coordinator** can submit and manage the request. Under the shipped
permissions, a **System Manager** creates and submits the `Maintenance Work Order`; a
**Maintenance Technician** starts and completes it but cannot create, submit, or cancel
it.

## Before starting

- Use a disposable training site with a fictional Building and Room.
- Prepare separate request-handler, System Manager, and Maintenance Technician accounts.
- Prepare a non-sensitive completion image.
- Keep procurement cost at zero for the basic exercise.

## Exercise: resolve one facility fault

1. Create a `Maintenance Request` with Building, Room, issue type, priority, and a clear
   description. Submit it as **Open**.
2. Sign in as System Manager, open the request, and choose **Create Work Order**. Enter
   planned dates, an assignee, and the work description, then submit it.
3. Confirm that the `Maintenance Work Order` is **Planned** and its source request is
   **In Progress**. Sign out of the System Manager account.
4. As Maintenance Technician, choose **Start Work**. Confirm that the order is
   **In Progress** and its actual start date was recorded.
5. Choose **Mark as Completed**. Enter the actual end date, completion notes, and the
   sanitized completion photo.
6. Confirm that the order is **Completed**, the request is **Closed**, and the order
   records who verified completion and when.

## Decisions and exceptions

- **Assigned** requires an assignee. **Resolved** and **Closed** require resolution
  notes.
- **Load Material Template** adds suggested lines to a draft request or work order. It
  does not buy, receive, reserve, or pay for materials.
- **Start Work** records the actual start date. **Mark as Completed** records the end
  date and requires a completion photo; the end date cannot precede the start date.
- Positive procurement lines create `Maintenance Cost Ledger` entries and one direct
  `Accommodation Ledger` memo when work is completed. They do not create a Purchase
  Invoice, Payment Entry, or General Ledger posting.
- Use an active `Subcontractor Service Contract` and `Subcontractor Service Order` for
  an external visit. Its **Start Work**, **Mark as Completed**, and **Mark Missed**
  actions are separate from the internal work order.
- `Maintenance Inspection Report` is limited to System Manager.

Cancelling a work order requires a reason, reopens a source request that is still
**In Progress** or **Closed**, and reverses its operational cost records. Preserve the
original and reversal rows.

## Evidence of completion

Show the submitted request and linked work order, the **Planned** to **In Progress** to
**Completed** history, actual dates, completion photo, verifier, and the closed source
request. For the zero-cost exercise, confirm that no maintenance cost row was created.

## Related links

- [Accommodation operations](accommodation.md)
- [Safety operations](safety.md)
- [Scheduled automation](../reference/automation.md)
