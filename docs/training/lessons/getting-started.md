# Getting Started in Apex

## Audience

New Desk operators, reviewers, and site administrators.
Portal-only Drivers are outside this lesson and use the
[Driver and Worker Portals](../portals-masar-driver.md) guide.

## Outcome

Use the exact available entry path supplied for a trainer-selected authorized
DocType, then distinguish navigation from permission. The path may be a named
workspace that contains the route or the exact Awesome Bar DocType.

## Prerequisites

- A training account with the same roles as the intended job.
- Access to a non-production training site.
- The [module, workspace, and route reference](../../reference/routes-workspaces.md).
- The [permissions and role reference](../../reference/permissions.md).
- The [training role map](../README.md#role-tracks).

## Core concepts

**Desk** is Frappe's signed-in working area. A **Workspace** groups shortcuts,
reports, charts, and onboarding steps. A **DocType** defines a business record.
A portal is a focused web interface for a specific audience.

Seeing a workspace, shortcut, page, or portal does not grant access to its
records. Frappe DocPerm, workflow rules, and Apex row scope decide what the user
can read or change.

Use the **Awesome Bar** to find a DocType or page when you know its name. Use the
workspace when you need the normal business path and related context.

## Exercise

1. Sign in with the training account.
2. Ask the trainer for one authorized DocType and its exact available entry
   path from the training role map and current Desk.
3. If the supplied path names a workspace that contains the route, open that
   workspace and follow its navigation to the selected DocType.
4. Otherwise, use the supplied exact Awesome Bar DocType even when the role has
   another assigned workspace.
5. Open the selected List view and one record the account is allowed to read.
6. Identify the screen as Desk rather than a portal, then compare its visible
   navigation with the canonical permission reference.
7. Return to the starting workspace or Awesome Bar entry without changing the
   record.

## Verification

The learner can identify:

- the exact workspace route or Awesome Bar entry used to reach the record;
- the trainer-selected authorized DocType that stores the record;
- whether the screen is Desk or a portal;
- why visible navigation is not proof of read, write, or submit access.

## Cleanup and data safety

This exercise is read-only and creates no records. Do not change roles, User
Permissions, or existing business records to make a training screen visible.
Report an access mismatch to the trainer or administrator.
