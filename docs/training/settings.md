# Configure Apex Safely

## Outcome

Choose the setting that owns a business behavior, test one controlled change, prove the
result with the affected persona, and restore the baseline.

This guide is for System Managers and designated process owners on a non-production site.

## Choose the setting by outcome

Apex ships one settings record per module, and everything a module configures lives inside
its own record.

- **Habitat Settings** — housing defaults, company and cost center, custody handoffs, safety
  thresholds, notifications, contact details, optional passport scanning, the internal store
  engine, the General Ledger posting gate, snapshot retention, and payment routing.
- **Salis Settings** — fleet defaults, alert thresholds, approvals and authority limits,
  boarding, driver access, optional web push, driver portal appearance, approved external
  origins, and messaging configuration.
- **Logistay Settings** — the telecom alert windows.

A setting changes the site, not one user. Record the old value, owner, reason, expected
result, test persona, and rollback before saving.

## High-risk settings

Keep General Ledger posting, messaging credentials, and automatic target submission disabled
until the responsible Finance, HR, Legal, and IT owners approve the complete process.

Recovering vehicle damage from pay is not configured here. It runs on the lending
application's own loan, and a site without that application refuses to raise the recovery
rather than inventing one.

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

1. Record the current accent under **Driver Portal Appearance** in **Salis Settings**.
2. Identify the fictional worker who will verify the change.
3. Change only the accent on the training site.
4. Open the worker experience with a freshly issued training link.
5. Confirm the identity, language, contrast, and primary actions remain usable.
6. Restore the original accent.
7. Reload the worker experience and prove the baseline returned.

Do not use a production link or capture the training credential in evidence.

## Background follow-up

Start from the business record that should be due. Confirm its status, date, owning
setting, and expected output. Then use the **Scheduled Job Type** screen to identify which
Apex job follows that business condition and what it may create or update, and check the
source record and **Scheduled Job Log** before rerunning anything. Do not create the
expected output by hand to make a dashboard change.

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
- [Trainer setup and reset](trainer-setup.md)
