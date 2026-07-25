# Copyright (c) 2026, AFMCO and contributors
from frappe.utils import get_datetime

# [#l4tfhr]

# The shipped feed starts at 2.0.0 and never reaches back: the pre-2.0 notes are
# retired product history and their popup folders are gone from disk, so the Desk
# "What's New" popup and this bell feed now agree on the same 2.x floor.
_RELEASES = [
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
        "link": "/app/logistay",
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
