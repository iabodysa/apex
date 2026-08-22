# Configure Apex Safely

## Outcome

Choose the setting that owns a business behavior, test one controlled change, prove the
result with the affected persona, and restore the baseline.

This guide is for System Managers and designated process owners on a non-production site.

## Choose the setting by outcome

- **Apex Settings** — shared company behavior, General Ledger posting gate, and snapshot
  retention.
- **Habitat Settings** — housing defaults, custody handoffs, safety thresholds,
  notifications, contact details, and optional passport scanning.
- **Salis Settings** — fleet defaults, alert thresholds, approvals, boarding, driver access,
  and optional web push.
- **Apex Integration Settings** — approved external origins and messaging configuration.
- **Payment Routing Settings** — controlled creation of the approved native payment target.
- **Salary Deduction Policy** — legal and HR gate for operational recovery through payroll.
- **Driver Portal Theme** — shared worker and driver appearance.

A setting changes the site, not one user. Record the old value, owner, reason, expected
result, test persona, and rollback before saving.

## High-risk settings

Keep General Ledger posting, salary deductions, messaging credentials, and automatic target
submission disabled until the responsible Finance, HR, Legal, and IT owners approve the
complete process.

For this release, keep **Payment Entry** as the payment target and target auto-submit off.
The target selection alone is not a complete field map. Do not use **Create Payment** until
Finance validates the mapping on the target site.

Integration origins do not grant data access. Authentication, roles, record permission, and
server-side scope continue to apply.

## Portal access is not a general setting

**Masar Worker Token** is a personal credential record. Save the intended holder, then use
the displayed **Issue Link and QR** or **Rotate Link and QR** action. Never type a token,
construct a portal URL, or edit credential fields directly.

If a link is exposed, rotate it and follow the organization's credential-incident process.
Do not include the old or new link in the incident record.

## Controlled exercise

1. Record the current **Driver Portal Theme** and accent.
2. Identify the fictional worker who will verify the change.
3. Change only the accent on the training site.
4. Open the worker experience with a freshly issued training link.
5. Confirm the identity, language, contrast, and primary actions remain usable.
6. Restore the original accent.
7. Reload the worker experience and prove the baseline returned.

Do not use a production link or capture the training credential in evidence.

## Background follow-up

Use the scheduled automation reference to identify which Apex
job follows a business condition, what enables it, and what record it may create or update.
Check the source record and **Scheduled Job Log** before rerunning anything.

An unchanged dashboard is not proof of failure. No source may be due, the feature may be
disabled, or the expected record may already exist.

## Completion evidence

- The correct settings record was selected for the requested outcome.
- Before and after values were recorded without credentials.
- The affected persona verified the result.
- The baseline was restored.
- No role, scope, payment, payroll, or integration boundary changed as a side effect.

## Related guides

- [IT Operations track](tracks/it-operations.md)
