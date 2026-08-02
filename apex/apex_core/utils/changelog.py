# Copyright (c) 2026, AFMCO and contributors
from frappe.utils import get_datetime

# [#l4tfhr]

# The shipped feed starts at 2.0.0 and never reaches back: the pre-2.0 notes are
# retired product history and their popup folders are gone from disk, so the Desk
# "What's New" popup and this bell feed now agree on the same 2.x floor.
_RELEASES = [
    {
        "title": "Apex 2.2.3 — The route supervisor screen can be linked to, and it fits the device you open it on.",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-08-02 18:06:31",
    },
    {
        "title": "Apex 2.2.2 — The portals show a live map, one denial screen, and clearer empty cards.",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-08-02 16:48:21",
    },
    {
        "title": "Apex 2.2.1 — Corrections to what you see and who can see it.",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-08-02 13:44:04",
    },
    {
        "title": "Apex 2.2.0 — The desk opens on a single Apex page that lists the portals, with five module workspaces beneath it instead of nine unrelated ones.",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-08-02 11:02:58",
    },
    {
        "title": "Apex 2.1.26 — Safety task instructions no longer name a client or a client policy.",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-08-02 01:45:32",
    },
    {
        "title": "Apex 2.1.25 — Documentation update.",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-08-01 21:19:15",
    },
    {
        "title": "Apex 2.1.24 — The setup wizard and the worker and driver link screens now read in Arabic instead of falling back to English.",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-08-01 18:45:29",
    },
    {
        "title": "Apex 2.1.23 — The setup wizard can now create demo data to explore Apex with, and Apex Settings can remove every record it created.",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-08-01 16:49:10",
    },
    {
        "title": "Apex 2.1.22 — Documentation update.",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-08-01 12:36:17",
    },
    {
        "title": "Apex 2.1.21 — Typing a transport request no longer disappears while the screen refreshes, safety verdicts survive a reload, photos are refused before upload if the server would reject them, and refusals now arrive in the language of the page.",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-08-01 09:06:38",
    },
    {
        "title": "Apex 2.1.20 — Transport request authorization now says who may approve, fleet roles can pick a project again, uploaded photos must really be images, and telecom billing works for a period that has already closed.",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-08-01 07:39:49",
    },
    {
        "title": "Apex 2.1.19 — Housing records can be created from the form again, portal dialogs keep the keyboard inside them, and a refused safety round now says why.",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-08-01 05:39:15",
    },
    {
        "title": "Apex 2.1.18 — The personal worker link the demo seeder prints now opens the portal instead of failing.",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-08-01 03:16:45",
    },
    {
        "title": "Apex 2.1.17 — The release feed's own test no longer breaks when the release table grows.",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-08-01 02:14:36",
    },
    {
        "title": "Apex 2.1.16 — The repository now ships the application and the application's own tests, and nothing else.",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-08-01 01:30:38",
    },
    {
        "title": "Apex 2.1.15 — Five portals move onto one shared design, two housing reports ask a single scope authority, and the demo seeder now explains why it skipped.",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-08-01 00:50:14",
    },
    {
        "title": "Apex 2.1.14 — The Arabic across the app now reads the way a Saudi employee speaks",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-31 20:27:09",
    },
    {
        "title": "Apex 2.1.13 — A damage deduction can no longer clear a worker's advance on paper while the money is still owed on the books",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-31 19:01:51",
    },
    {
        "title": "Apex 2.1.12 — The portals share one set of colours, one keyboard outline and one theme switch",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-31 18:21:04",
    },
    {
        "title": "Apex 2.1.11 — Missing workspace links are back, and the damage register opens for the finance role that approves it",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-31 16:47:48",
    },
    {
        "title": "Apex 2.1.10 — The published pages are checked like code, the route supervisor portal moves onto the shared design, and the upgrade runbook was rehearsed against a live site",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-31 15:22:35",
    },
    {
        "title": "Apex 2.1.9 — The integration guide stops asking browsers to hold a secret, and the whole codebase settles on one indentation style",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-31 14:20:58",
    },
    {
        "title": "Apex 2.1.8 — The app now describes all four of its modules wherever it describes itself",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-31 10:49:58",
    },
    {
        "title": "Apex 2.1.7 — A name lookup that could answer without checking the database is now refused before it ships",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-31 09:50:29",
    },
    {
        "title": "Apex 2.1.6 — The last records named after retired document types now carry the names those documents actually have",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-31 08:54:03",
    },
    {
        "title": "Apex 2.1.5 — Alerts no longer point at records their audience cannot open, and an incompatible framework argument is caught in seconds instead of mid-suite",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-31 07:37:20",
    },
    {
        "title": "Apex 2.1.4 — permission decisions that explain themselves in the code, and repository gates that are themselves guarded",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-31 06:00:00",
    },
    {
        "title": "Apex 2.1.3 — one shared portal poller that rests with the tab, seeding that survives a bad row, and hook wiring you can check before a commit fails",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-31 04:00:00",
    },
    {
        "title": "Apex 2.1.2 — blank sidebars restored for three personas, portals that load fully offline, and a working fleet page menu",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-25 20:00:00",
    },
    {
        "title": "Apex 2.1.1 — SIM and telecom folded into Custody, damaged-item cost recovery via Employee Advance, and a steadier app to maintain",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-25 05:00:00",
    },
    {
        "title": "Apex 2.1.0 — a lighter, faster-migrating app with safer document approvals and Arabic-correct onboarding tours",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-23 18:40:00",
    },
    {
        "title": "Apex 2.0.4 — Guided first-time setup, ready accommodation supplies, and preserved Item Group organization",
        "app_name": "apex",
        "link": "/app/launchpad",
        "creation": "2026-07-20 18:40:00",
    },
    {
        "title": "Apex 2.0.3 — security and reliability improvements",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-19 12:00:00",
    },
    {
        "title": "Apex 2.0.2 — security and reliability improvements",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-18 18:00:00",
    },
    {
        "title": "Apex 2.0.1 — simpler Logistay records, consistent task-focused portals, fleet employee self-service, and passwordless barcode access for drivers and workers",
        "app_name": "apex",
        "link": "/driver",
        "creation": "2026-07-18 00:15:00",
    },
    {
        "title": "Apex 2.0.0 — a generational release: a new Logistay workforce module reads client attendance into one standard record with a governed exception workbench and carries the accommodation and logistics billing cycle (rate cards, reconciliation, ZATCA-shaped invoicing, and WPS payroll under a governance layer), with clearer plainer names and task-first daily workspaces across the app, native expiry alerts by email and in-app, one shared foundation behind the five worker and driver portals, and stronger safeguards throughout",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-07-10 09:00:00",
    },
]


# [#a0cv0f]
_FEED_TITLE_MAX = 140

# [#ojxrjf]
_FEED_MAX = 20


def _clip_title(title):
    title = title.strip()
    if len(title) <= _FEED_TITLE_MAX:
        return title
    return title[: _FEED_TITLE_MAX - 1].rstrip() + "…"


def get_changelog_feed(since):
    """
    Returns Apex release items newer than `since`, newest first, capped at
    `_FEED_MAX`. Registered via hooks.py get_changelog_feed hook.
    Frappe's fetch_changelog_feed() calls this and deduplicates by exact field match.
    """
    since_dt = get_datetime(since)
    items = [
        {**r, "title": _clip_title(r["title"])}
        for r in _RELEASES
        if get_datetime(r["creation"]) > since_dt
    ]
    return items[:_FEED_MAX]
