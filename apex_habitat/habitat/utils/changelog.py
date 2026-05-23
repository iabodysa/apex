from frappe.utils import get_datetime

# Static release feed for Apex Habitat.
# Each entry has: title, app_name, link, creation (ISO datetime string).
# creation must be a fixed past timestamp so deduplication is stable across repeated calls.
# fetch_changelog_feed() checks frappe.db.exists("Changelog Feed", {title, app_name, link, posting_timestamp})
# before inserting — fully idempotent.

_RELEASES = [
    {
        "title": "Apex Habitat v0.4.0 — Accommodation Setup & Bulk Generation",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-05-23 00:00:00",
    },
    {
        "title": "v0.4.0: Floor Plan child table and bulk room/bed generator added",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-05-23 00:01:00",
    },
    {
        "title": "v0.4.0: Room readiness status and supervisor inventory notes added",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-room",
        "creation": "2026-05-23 00:02:00",
    },
    {
        "title": "v0.4.0: Room Label print format added",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-room",
        "creation": "2026-05-23 00:03:00",
    },
    {
        "title": "v0.3.1: Intercompany Asset Movement Register and 8 report shortcuts added",
        "app_name": "apex_habitat",
        "link": "/app/facility-asset-movement",
        "creation": "2026-05-20 00:00:00",
    },
    {
        "title": "v0.3.0: Company context, 5 new operational reports, Employee housing links added",
        "app_name": "apex_habitat",
        "link": "/app/habitat-settings",
        "creation": "2026-05-18 00:00:00",
    },
]


def get_changelog_feed(since):
    """
    Returns Apex Habitat release items newer than `since`.
    Registered via hooks.py get_changelog_feed hook.
    Frappe's fetch_changelog_feed() calls this and deduplicates by exact field match.
    """
    since_dt = get_datetime(since)
    return [r for r in _RELEASES if get_datetime(r["creation"]) > since_dt]
