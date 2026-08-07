# Apex Troubleshooting

Start with evidence. Do not change permissions, data, scheduler state, or
deployment state during the first diagnostic pass.

## Safety boundary

- Work on the exact affected Frappe site and record the local time of the issue.
- Redact passwords, API secrets, personal portal tokens, cookies, employee
  identity data, and attachment contents.
- Do not use `show-config`; it can expose site configuration.
- Do not run migrations, builds, cache clears, scheduler triggers, database
  consoles, job purges, or arbitrary `execute` calls as diagnosis.
- Do not delete submitted documents or system-written ledgers. Follow the
  document's cancel, amendment, or reversal path.

## Read-only first pass

Run these commands from the bench directory. Replace `<site>` with the affected
site name.

```bash
git -C apps/apex rev-parse HEAD
git -C apps/apex status --short
bench --site <site> list-apps
bench --site <site> scheduler status
bench doctor --site <site>
bench show-pending-jobs --site <site>
```

Record the observed output. These checks establish source revision, installed
apps, scheduler state, worker health, and queued work. They do not prove that a
specific business record qualifies for automation.

In Desk, inspect these native records without editing them:

- **Error Log** for the matching timestamp and operation.
- **Scheduled Job Type** and **Scheduled Job Log** for a scheduler issue.
- **Workflow Action** for a missing approval action.
- **Notification Log** for an in-app notice.
- **Email Queue** for an email transport issue.
- **Version** and document timeline comments for an unexpected record change.
- **Role Permission Manager** and **User Permission** for an access issue.

## Access denied or missing navigation

Access has separate layers:

1. Workspace, page, or portal navigation decides whether an entry point is
   visible.
2. DocPerm decides which document operations a role may perform.
3. Workflow state can restrict the available action.
4. User Permission and Apex row-scope hooks can restrict Project, Building, or
   Company records.
5. Portal controllers apply their own identity and role checks.

Compare the affected surface with the
[route and workspace reference](routes-workspaces.md) and the
[permission reference](permissions.md). Record the exact user, role list,
DocType, document name, route, and attempted action.

Do not add System Manager or remove row scope as a diagnostic shortcut. A broad
grant can hide the real mismatch and create unrelated access.

## Portal fails to open or shows the wrong data

1. Confirm the exact route is shipped in the
   [route reference](routes-workspaces.md#served-portal-routes).
2. In browser developer tools, record the failing request URL, method, status,
   and response error. Do not copy request credentials.
3. Record missing or failed `/assets/apex/` requests separately from API
   failures. A page-shell failure and an authorization failure have different
   owners.
4. For a signed-in portal, confirm the User is enabled and has the required
   route role.
5. For a worker or driver portal, confirm the source Employee or Salis Driver
   is active and linked as expected. Never print or replace the personal token
   during diagnosis.

If source, controller, and compiled asset revisions appear different, stop
after collecting evidence and hand the case to the release operator. Do not
build or clear caches as an unreviewed production experiment.

## Scheduled job appears not to run

1. Confirm scheduler and workers with the read-only commands above.
2. Find the exact dotted callable in the
   [automation reference](automation.md).
3. Check Scheduled Job Log and Error Log at the expected cadence.
4. Check the job's qualifying records and gate. A clean no-op is normal when no
   record qualifies.
5. Check its idempotency key. An existing ledger row, snapshot, open
   assignment, or draft installment may be the intended reason no second
   record was created.

Do not manually trigger a production job until its current behavior,
idempotency, affected record count, and maintenance window have been reviewed.

## Expected no-op cases

- Daily accommodation cost allocation needs a submitted open Housing
  Assignment, Employee, Building, positive capacity, and positive configured
  annual cost.
- Occupancy Snapshot skips a Building with no rooms or an existing snapshot for
  that date.
- Cleaning generation skips an existing non-cancelled Building and date pair.
- The weekly custody digest email stops when
  `Habitat Settings.enable_email_notifications` is off.
- Monthly employee recovery stops when the Damage rule is inactive, the
  Employee Advance source fields are unavailable, no paid balance remains, no
  wage is known, or the pay period has no deduction capacity.
- The five-minute boarding job normally changes nothing because the current
  worker flow writes Boarded directly and does not create Worker Claimed rows.
- The SIM digest needs an assigned Suspended or Lost SIM and an enabled SIM
  Operations User.

## Notification or email is missing

Separate the channels:

- An **assignment** is a native ToDo on the source document, shown in the
  assignee's desk queue.
- **Notification Log** is an in-app Frappe notification.
- **Email Queue** is the outbound email path.
- A timeline comment is attached to the source document.

For explicit Apex emails, confirm the master
`Habitat Settings.enable_email_notifications` switch, the recipient User, and
the site's outgoing Email Account. Native Notification and Auto Email Report
records also have their own enabled state.

An in-app notification can exist even when email transport is unavailable.
Conversely, some scheduled jobs intentionally update status without sending a
notice. The [automation reference](automation.md) identifies each channel.

## An assignment stays open

Watcher jobs queue work as native ToDo assignments on the source document and
close them again when the condition clears. The drain point differs by DocType:

- **Salis Vehicle**, **Salis Driver**, and **Fuel Quota** drain in the daily
  `reconcile_operations_alerts` pass, and only when no watcher's condition
  still holds for that document.
- **Maintenance Request**, **Vehicle Suspension**, **Building**, **Scheduled
  Task Instance**, and **Rental Office** drain inside their own writer jobs,
  so an assignment persists until that job's next pass — monthly for Rental
  Office.

Confirm the source condition and the owning job's cadence before treating an
open assignment as scheduler failure.

## Housing totals or cost history looks wrong

1. Compare submitted Housing Assignments with open checkout state.
2. Check Room and Building capacity before comparing occupancy percentage.
3. Check whether the Building has rooms; weekly building reconciliation and
   daily snapshots skip roomless buildings.
4. Trace Accommodation Ledger rows through `source_doctype`, `source_name`,
   assignment, posting date, building, and ledger type.
5. Preserve reversal rows. Do not remove an original ledger row to make a total
   look correct.

The weekly occupancy sync corrects live counters. The daily Occupancy Snapshot
preserves history. They serve different purposes.

## Fuel or rental totals look wrong

- Trace each Fuel Consumption Ledger row to its Fuel Daily Log or Fuel Request.
- A Done Fuel Request can be accrued even when it is older than the Daily Log
  two-day window; the request path processes any unledgered submitted Done row.
- Fuel reconciliation uses the current month and the configured overage margin.
- Daily rental accrual requires the latest submitted Rental Vehicle Movement to
  be Receipt.
- Monthly rental reconciliation checks the previous closed month and does not
  settle rows. Rental Settlement submission owns that link.
- Keep original and reversal rows together when reconciling totals.

## SIM state looks wrong

Treat **SIM Custody Assignment** as the event history and **SIM Card** as the
current projection.

1. Find the latest submitted custody action.
2. Compare its Action, Employee or Project, effective Cost Center, and action
   date with the SIM Card's current fields.
3. Confirm the SIM belongs to the expected Telecom Contract and Company.
4. Correct a mobile number on the same SIM Card. Do not create another SIM just
   because the number changed.

## Portal rate-limit address trust is uncertain

IP-based portal controls are safe only when the public proxy supplies a
trustworthy client address and removes caller-controlled forwarding values.

The `check_request_ip_trust` endpoint is diagnostic only. Its result can be
inconclusive when forwarding headers are absent or cross multiple trusted hops,
so it cannot approve production proxy trust by itself.

Before enabling forwarded-header trust, independently review the active proxy
configuration and test the complete public path. Prove that the edge replaces
an external caller's forwarding value, preserves only the intended trusted-hop
chain, and produces the expected address at the application. Keep
forwarded-header trust disabled when any result is ambiguous.

## Escalation package

Provide:

- affected Frappe site and timestamp with timezone;
- source revision and installed-app list;
- user and roles, without credentials;
- route or DocType and document name;
- expected and observed state;
- Error Log or Scheduled Job Log name;
- redacted browser request status and screenshot where relevant;
- the smallest repeatable sequence that reproduces the issue.

Do not include tokens, cookies, passwords, private email addresses, or raw
personal documents.

## Related references

- [Business glossary](glossary.md)
- [Scheduled automation](automation.md)
- [Permissions and roles](permissions.md)
- [Modules, workspaces, and routes](routes-workspaces.md)
