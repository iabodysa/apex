# Scheduled Automation Reference

This page lists every Apex callable registered in
`scheduler_events` in `apex/hooks.py`. The list and its cadences are compared
against that declaration before a release, so a job cannot run undocumented and
a retired job cannot linger here. What each job does, and the condition that
makes it a no-op, is written by hand.

Scheduled frequency does not guarantee that a record will change. Each job
first checks its source records and, where applicable, a setting or
idempotency key.

## Effect terms

- **Check** reads current records and evaluates a condition.
- **Enqueue** sends work to a background queue.
- **Create** inserts a document, ledger row, snapshot, comment, or assignment.
- **Update** changes an existing document.
- **Notify** creates an in-app notice or sends email.
- **Cleanup** deletes bounded, explicitly selected housekeeping records.
- **Gate** exits without action until a setting or required setup is ready.

## Inventory

| Cadence | Apex Core | Habitat | Salis | Logistay | Total |
|---------|-----------|---------|-------|----------|-------|
| Daily | 1 | 12 | 8 | 1 | 22 |
| Weekly | 0 | 3 | 2 | 0 | 5 |
| Monthly | 1 | 0 | 2 | 0 | 3 |
| Cron | 1 | 0 | 1 | 0 | 2 |
| **Total** | **3** | **15** | **13** | **1** | **32** |

## Daily jobs

| Callable | Effect | Current behavior | Gate or limiting condition |
|----------|--------|------------------|----------------------------|
| `apex.habitat.tasks.cost.daily_accommodation_cost_allocation` | Enqueue, Create | Enqueues one deduplicated long-queue job per building. The worker writes daily, Operational Memo **Accommodation Ledger** rows by active assignment and positive annual cost type. | Requires a submitted assignment with no checkout, an employee, a building with positive capacity, and a positive configured cost. |
| `apex.habitat.tasks.maintenance.daily_building_license_expiry_check` | Update | Changes submitted **Building License** records from Active to Expiring Soon or Expired. | Reads the record lead time, then the Habitat Settings default. It does not send the expiry notice; native Notifications own that path. |
| `apex.habitat.tasks.maintenance.open_maintenance_escalation` | Check, Create, Update | Assigns each overdue open **Maintenance Request** to the Accommodation Manager queue as a native ToDo and adds a timeline comment. Thresholds are 24, 72, 168, and 336 hours for Critical, High, Medium, and Low. | Handles Open, Assigned, In Progress, and Reopened requests. A request already queued is not assigned twice, and the pass ends by closing assignments on requests no longer overdue. |
| `apex.habitat.tasks.residency.lease_expiry_watchlist` | Update | Changes a submitted Approved or Active **Lease** to Expired after its end date. | It does not send the lease notice; native Notifications own that path. |
| `apex.habitat.tasks.residency.idle_resident_aging` | Update, Notify | Recalculates idle days and the estimated accommodation cost on open or acknowledged **Idle Resident Report** records. Adds a timeline note every seventh idle day. | Timeline notes require `enable_operational_notifications`. Cost comes from existing Accommodation Ledger rows. |
| `apex.habitat.tasks.custody.consumable_custody_expiry_watch` | Check, Notify | Notifies every enabled Resident Supervisor in-app when an employee still holds a consumable beyond that article's lifespan. | Requires a positive stock-ledger balance and a positive `consumable_lifespan_months`. An unread notice with the same employee-and-article subject is not repeated per user. |
| `apex.habitat.tasks.scheduled_tasks.daily_scheduled_task_instance_generator` | Create | Creates **Scheduled Task Instance** records from active assignments and active template items. Daily, weekly, monthly, quarterly, and annual items use their period start as the due date. | Existing non-cancelled assignment, task, and due-date combinations are skipped. |
| `apex.habitat.tasks.occupancy.daily_occupancy_snapshot` | Create | Writes one daily **Occupancy Snapshot** per building, including occupants, capacity, room status counts, and unused-capacity cost. | Skips buildings with no rooms and an existing building/date snapshot. |
| `apex.habitat.tasks.cleaning.daily_cleaning_log_generator` | Create | Creates today's draft **Cleaning Log** for each active building with rooms and pre-populates its room rows. | Skips an existing non-cancelled building/date log. It never submits the log. |
| `apex.habitat.tasks.safety.daily_safety_task_compliance_scan` | Update, Create, Notify | Marks due **Scheduled Task Instance** records Overdue. High and Critical items are also assigned to the Safety Officer queue with an in-app notification beside the assignment. A second pass assigns active buildings with no submitted **Safety Round** in the trailing seven-day window and notifies Safety Officers and the building's responsible supervisor. | The overdue cutoff uses `safety_overdue_grace_days`. Timeline comments require operational notifications. Both queues reconcile at the end of the pass; the Building queue drains only when neither safety condition still holds. |
| `apex.habitat.tasks.safety.audit_remediation_deadline_watch` | Update, Notify | Marks submitted **Audit Remediation Plan** records Overdue after their deadline and notifies the internal owner and Accommodation Manager users in-app. | Closed by Client and already Overdue records are excluded. The timeline note requires operational notifications. |
| `apex.habitat.temporary_worker_engine.link_temporary_workers` | Update, Create, Notify | Matches an active **Temporary Worker** to an active Employee by passport, repoints supported housing and custody party links, backdates missed accommodation-cost rows, and marks the worker Linked. Unmatched workers past their window are marked Expired and HR users are notified in-app. | A link requires a matching passport. Expiry notification uses HR Manager users, falling back to System Manager users. |
| `apex.salis.tasks.vehicle.idle_vehicle_watch` | Check, Create | Assigns an active **Salis Vehicle** with no submitted Dispatched or Completed trip in the recent window to the Fleet Supervisor queue and adds a timeline comment. | Uses `idle_vehicle_days`, default 7. A vehicle already queued is not assigned twice; the shared vehicle queue drains in `reconcile_operations_alerts`. |
| `apex.salis.tasks.fuel.unreverted_topup_watch` | Update, Notify | Changes an overdue temporary **Fuel Request** top-up to Reverted, adds a timeline comment, and notifies every enabled Fleet Supervisor in-app of the auto-revert. | Applies to unreverted Approved or Done top-ups whose revert due date has passed. Notify, not assign: the job has already fixed the condition it found. |
| `apex.salis.tasks.attendance.missing_attendance_watch` | Check, Create | Assigns each active **Salis Driver** with no submitted **Driver Attendance** today to the Fleet Supervisor queue and adds a timeline comment. | A driver already queued is not assigned twice; the driver queue drains in `reconcile_operations_alerts` once attendance lands or the driver is no longer Active. |
| `apex.salis.tasks.vehicle.vehicle_compliance_expiry_watch` | Check, Create | Scans **Salis Vehicle Compliance** rows up to the configured horizon and assigns the parent vehicle to the Fleet Supervisor queue — high priority when already expired, medium when approaching. | Uses `alert_lead_days`, default 30. One open assignment per vehicle and holder, even when several compliance rows qualify; the shared vehicle queue drains in `reconcile_operations_alerts`. |
| `apex.salis.tasks.workshop.workshop_overstay_watch` | Check, Create, Update | Assigns the open submitted maintenance **Vehicle Suspension** of a vehicle still Stopped or Under Maintenance past the threshold to the Fleet Supervisor queue, then closes assignments on stops no longer overstaying. | Uses `workshop_overstay_days`, default 14. This job is the only queuer of Vehicle Suspension, so it reconciles its own queue. |
| `apex.salis.tasks.alerts.reconcile_operations_alerts` | Update | Closes open Fleet Supervisor assignments on **Salis Vehicle**, **Salis Driver**, and **Fuel Quota** records whose underlying condition has cleared, then publishes a board refresh. | A document stays queued while any writer's condition still holds: recent idleness or a compliance row inside the lead window, a missing attendance today, a still-breached current-month quota. Vehicle Suspension and Rental Office reconcile inside their own writer jobs. |
| `apex.logistay.tasks.sim_alerts.assigned_suspended_or_lost_watch` | Notify | Creates one in-app **Notification Log** per enabled SIM Operations User when assigned SIM cards are Suspended or Lost. The subject carries the total and the body lists up to 50 SIMs. | Requires at least one qualifying SIM and one enabled role holder. A manual rerun creates another current digest; there is no additional dedupe key. |
| `apex.salis.fuel_engine.accrue_fuel_consumption` | Create, Update | Writes **Fuel Consumption Ledger** rows from Fuel Daily Logs for yesterday or today and from every submitted Done Fuel Request not yet ledgered. Marks processed requests as ledgered. | Source type and source name form the ledger idempotency key. A Done request is not limited to the two-day Daily Log window. |
| `apex.salis.rental_engine.daily_rental_accrual` | Create | Writes one daily, no-GL **Rental Accrual Ledger** memo for each rented vehicle whose latest submitted movement is a Receipt. | Skips a vehicle/date already accrued and any vehicle whose latest movement is a Return. |
| `apex.apex_core.utils.workflow_utils.cleanup_orphaned_workflow_actions` | Cleanup | Deletes only Open **Workflow Action** rows whose source document is missing or has moved beyond the recorded workflow state, then clears Workflow Action notifications. | Completed actions remain as audit history. Each active workflow is isolated from failures. |

## Weekly jobs

| Callable | Effect | Current behavior | Gate or limiting condition |
|----------|--------|------------------|----------------------------|
| `apex.habitat.tasks.occupancy.weekly_occupancy_sync` | Update | Recalculates Room occupancy and status, then Building occupant count and occupancy percentage from submitted open assignments. | Building counters are skipped when the building has no rooms. |
| `apex.habitat.tasks.custody.weekly_custody_digest` | Gate, Notify | Emails each enabled responsible supervisor a building-level custody summary: open and overdue issues, value still held, and month-to-date assessed damage. | Requires the master email switch and a responsible supervisor on the building. It does not change custody records. |
| `apex.habitat.tasks.safety.weekly_safety_coverage_gate` | Gate, Check, Create, Notify | Assigns each active building without a submitted Weekly **Safety Round** in the current site week to the Safety Officer queue, with an in-app notification beside the assignment. | `require_weekly_all_building_coverage` defaults on but an explicit false value disables the check. The Building queue drains only when neither safety condition still holds. It does not block document submission. |
| `apex.salis.tasks.vehicle.vehicle_utilization_summary` | Check, Create | Logs each active vehicle's trip count and distance from today minus seven days through today. Assigns a vehicle with zero trips to the Fleet Supervisor queue. | It does not persist a utilisation-summary document. Only submitted Dispatched or Completed trips are counted; the shared vehicle queue drains in `reconcile_operations_alerts`. |
| `apex.salis.utilisation_engine.weekly_vehicle_utilisation_snapshot` | Create | Writes one **Vehicle Utilisation Snapshot** per active vehicle for the trailing seven days, using Completed trips and distinct trip days. | Skips an existing vehicle/snapshot-date row. |

## Monthly jobs

| Callable | Effect | Current behavior | Gate or limiting condition |
|----------|--------|------------------|----------------------------|
| `apex.salis.fuel_engine.monthly_fuel_reconciliation` | Check, Create | Compares each current-month active **Fuel Quota** with Fuel Consumption Ledger litres and assigns a quota breached beyond the permitted margin to the Fleet Supervisor queue at high priority. | The margin defaults to 5 percent. A quota already queued is not assigned twice; the quota queue drains in `reconcile_operations_alerts` once the breach clears. No GL entry is posted. |
| `apex.salis.rental_engine.monthly_rental_reconciliation` | Check, Create, Update | Totals unsettled original rental accrual rows for the previous closed month and assigns each **Rental Office** still owing to the Fleet Supervisor queue, the assignment carrying the outstanding amount. An office that settles drains on the next pass. | It does not settle rows or post to the General Ledger. Submission of a Rental Settlement owns the stamping step. |
| `apex.apex_core.utils.employee_recovery.monthly_employee_recovery_run` | Gate, Create | Queues one draft **Additional Salary** deduction installment per eligible open **Employee Advance** and pay period. It never submits the installment. | No-op unless the Damage rule in Salary Deduction Policy is active and the Employee Advance source-link customization exists. Amount is bounded by paid outstanding balance, wage, existing deductions, policy limits, and any agreed installment. |

## Cron jobs

| Schedule | Callable | Effect | Current behavior | Gate or limiting condition |
|----------|----------|--------|------------------|----------------------------|
| `*/5 * * * *` | `apex.salis.api.boarding_flow.auto_confirm_claimed_boardings` | Update, Notify | Converts old **Trip Boarding State** rows from Worker Claimed to Boarded after the configured timeout and publishes a realtime update. | The current worker flow writes Boarded directly and creates no Worker Claimed rows. The job is therefore normally inert; it acts only when legacy or externally created Worker Claimed rows exist. |
| `0 23 * * *` | `apex.apex_core.utils.access_log_cleanup.purge_oversized_access_logs` | Cleanup | Deletes **Access Log** rows whose combined page, columns, and filters payload exceeds the configured byte threshold. Work is bounded and payload content is never returned or logged. | Defaults: threshold 1,000,000 bytes, batch size 500, maximum 20 batches. Native age-based Log Settings cleanup remains separate. |

## Related references

- [Permissions and role reference](permissions.md)
- [Modules, workspaces, and routes](routes-workspaces.md)
- [Business glossary](glossary.md)
- [Troubleshooting](troubleshooting.md)
