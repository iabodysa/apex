# Workspace Authoring

Apex workspaces organize daily work by domain. They make records and pages
discoverable; they do not grant document access.

The [workspace reference](../reference/routes-workspaces.md#workspaces) is the
canonical inventory of shipped workspaces, hierarchy, order, and visibility
roles.

## Where a workspace lives

A shipped Apex workspace is standard JSON under its owning module:

```text
apex/<module>/workspace/<workspace>/<workspace>.json
```

Navigation is expressed in the native fields only — Apex adds no workspace
mechanism of its own.

Workspace visibility is not authorization. The linked DocType, report, page,
and API must enforce its own permissions and row scope.

## Page order

Use this task-first order unless the workspace has a clear operational reason
to differ:

1. Getting Started
2. Headline chart
3. Quick Actions
4. Key Metrics
5. Daily Tasks
6. Key Reports
7. Master Data

Put setup and durable reference data after daily work. A system-written ledger
or snapshot belongs under Key Reports, never under Daily Tasks: a workspace
must not offer a create path into a record only the engine may write.

## Links and shortcuts

Choose the native target that matches the surface:

- Link a DocType for record entry or a list.
- Link a Report or Dashboard for derived information.
- Link a Desk Page for a focused operator console.
- Use a URL shortcut for a portal route.

A portal shortcut only opens a URL. Its Frappe route controller must perform
the entry check, and every backing API must check permissions and row scope.
Use the
[shortcut and route tables](../reference/routes-workspaces.md#workspace-portal-shortcuts)
instead of duplicating route details in a workspace guide.

## Source language

Keep Workspace JSON labels and descriptions in English. Add user-facing Arabic
to `apex/translations/ar.csv`. Reuse short, stable source strings where the same
meaning appears in more than one workspace.

## Change workflow

1. Confirm the workspace belongs to an existing module and domain root.
2. Define its audience from actual DocPerm and page access, not job-title
   assumptions.
3. Add the standard Workspace JSON and its linked records.
4. Add or update English source strings and Arabic translations.
5. Migrate a disposable site and inspect the rendered Desk navigation.

[Modules, workspaces, and routes](../reference/routes-workspaces.md) needs no
step of its own: it is generated from the Workspace, Page and `www/` files
themselves, so a workspace added, renamed or retired reaches it with the change
rather than after it. Do not hand-edit that page.

Apply the standard records to a site:

```bash
bench --site <site> migrate
bench --site <site> clear-cache
```

## Rename and removal

Frappe imports standard Workspace JSON during migration, but deleting or
renaming a file may leave the previous database record and child links behind.
Ship an idempotent migration patch for a rename or removal, then verify both a
fresh install and an upgraded site.
