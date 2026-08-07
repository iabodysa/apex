# IT Operations Track

## Audience

Site administrators and IT staff who support Apex access, navigation, portals,
and background processing.

## Outcome

Support users without confusing navigation, role grants, row scope, workflow,
or automation.

## Prerequisites

- Administrator access to a non-production site.
- A separate training account for each persona being tested.
- Change approval for any role, User Permission, or settings change.

## Learning path

1. [Frappe Foundations](../foundations.md)
2. [Settings and Desk Pages](../settings.md)
3. [Driver and Worker Portals](../portals-masar-driver.md)
4. [Modules, Workspaces, and Routes](../../reference/routes-workspaces.md)
5. **Role Permissions Manager** (`/app/permission-manager`)

Use the reference pages as the source for shipped navigation and permission
claims. Do not copy their tables into local support notes.

## Practice checkpoint

Choose one operational persona. With that persona's training account:

1. Confirm the expected workspace or portal entry point.
2. Open one permitted record and attempt no write.
3. Identify the DocPerm role, row-scope rule, and workflow owner.
4. Compare the result with an administrator account.
5. Record any mismatch as a configuration or product defect; do not grant a
   broad role as a shortcut.

## Verification

The trainee can explain the difference between a workspace role, DocPerm,
User Permission, workflow action, and server-side portal scope.

## Data safety

Never troubleshoot with another person's personal portal link. Do not reveal,
copy, or log API secrets or personal-link tokens. Test access with dedicated
accounts and remove temporary role or User Permission changes through the
approved change process.
