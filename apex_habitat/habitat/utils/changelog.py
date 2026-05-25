from frappe.utils import get_datetime

# Static release feed for Apex Habitat.
# Each entry has: title, app_name, link, creation (ISO datetime string).
# creation must be a fixed past timestamp so deduplication is stable across repeated calls.
# fetch_changelog_feed() checks frappe.db.exists("Changelog Feed", {title, app_name, link, posting_timestamp})
# before inserting — fully idempotent.

_RELEASES = [
    # v0.8.3 ---------------------------------------------------------------
    {
        "title": "Apex Habitat v0.8.3 — Calendars, Room Readiness Kanban, Auto-Assignment & Event Notifications",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-25 15:00:00",
    },
    {
        "title": "v0.8.3: Calendar views for Scheduled Tasks, Building Licences, Service Orders, and Leases",
        "app_name": "apex_habitat",
        "link": "/app/scheduled-task-instance/view/calendar",
        "creation": "2026-05-25 15:01:00",
    },
    {
        "title": "v0.8.3: Room Readiness Kanban board for housekeeping turnover",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-room/view/kanban",
        "creation": "2026-05-25 15:02:00",
    },
    {
        "title": "v0.8.3: Auto-assignment rules for Maintenance and Resident Requests (disabled by default — add your team and enable)",
        "app_name": "apex_habitat",
        "link": "/app/assignment-rule",
        "creation": "2026-05-25 15:03:00",
    },
    {
        "title": "v0.8.3: New event notifications — request assigned, new request, waiting evidence, damage assessment (disabled by default)",
        "app_name": "apex_habitat",
        "link": "/app/notification",
        "creation": "2026-05-25 15:04:00",
    },
    # v0.8.2 ---------------------------------------------------------------
    {
        "title": "Apex Habitat v0.8.2 — Decentralized Internal Store Engine & Kanban Boards",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-stock-ledger",
        "creation": "2026-05-25 12:00:00",
    },
    {
        "title": "v0.8.2: Each building is now its own store — custody issue/return moves stock on the new Accommodation Stock Ledger",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-stock-ledger",
        "creation": "2026-05-25 12:01:00",
    },
    {
        "title": "v0.8.2: New Accommodation Material Transfer — ship stock between buildings (In Transit → Received) with availability checks",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-material-transfer",
        "creation": "2026-05-25 12:02:00",
    },
    {
        "title": "v0.8.2: Memo-only finance notification on cross-cost-center transfers (no GL Entry posted)",
        "app_name": "apex_habitat",
        "link": "/app/habitat-settings",
        "creation": "2026-05-25 12:03:00",
    },
    {
        "title": "v0.8.2: New Accommodation Stock Balance report — on-hand quantity and value per store and per employee custody",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-stock-balance/view/report",
        "creation": "2026-05-25 12:04:00",
    },
    {
        "title": "v0.8.2: Kanban boards for Resident Requests and Maintenance Requests — drag cards across status columns",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-resident-request/view/kanban",
        "creation": "2026-05-25 12:05:00",
    },
    # v0.8.0 ---------------------------------------------------------------
    {
        "title": "Apex Habitat v0.8.0 — Supplier Recovery, Native Notifications & Engine Insights",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-25 09:00:00",
    },
    {
        "title": "v0.8.0: Supplier Cost Recovery report — monthly per-supplier cost with markup",
        "app_name": "apex_habitat",
        "link": "/app/supplier-cost-recovery/view/report",
        "creation": "2026-05-25 09:01:00",
    },
    {
        "title": "v0.8.0: Operational alerts moved to native timeline comments + Frappe Notifications",
        "app_name": "apex_habitat",
        "link": "/app/habitat-settings",
        "creation": "2026-05-25 09:02:00",
    },
    {
        "title": "v0.8.0: New occupancy-history engine + Occupancy Trend report",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-occupancy-snapshot",
        "creation": "2026-05-25 09:03:00",
    },
    {
        "title": "v0.8.0: Five bilingual hand-over print formats (custody, checkout, work order)",
        "app_name": "apex_habitat",
        "link": "/app/custody-issue",
        "creation": "2026-05-25 09:04:00",
    },
    {
        "title": "v0.8.0: System Administration workspace + new dashboard cards and charts",
        "app_name": "apex_habitat",
        "link": "/app/habitat-system-administration",
        "creation": "2026-05-25 09:05:00",
    },
    # v0.7.2 ---------------------------------------------------------------
    {
        "title": "Apex Habitat v0.7.2 — Reliability, Performance & Translation Hardening",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-24 21:00:00",
    },
    {
        "title": "v0.7.2: Submit/cancel is now all-or-nothing — no half-saved bills, checkouts, or work orders",
        "app_name": "apex_habitat",
        "link": "/app/utility-bill-entry",
        "creation": "2026-05-24 21:01:00",
    },
    {
        "title": "v0.7.2: Checkout clearance and cleaning reports load faster (N+1 queries removed)",
        "app_name": "apex_habitat",
        "link": "/app/checkout-pending-clearance",
        "creation": "2026-05-24 21:02:00",
    },
    {
        "title": "v0.7.2: Occupancy % and depreciation figures now computed live and capped correctly",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-occupancy-summary",
        "creation": "2026-05-24 21:03:00",
    },
    {
        "title": "v0.7.2: Stronger per-record permissions on room updates, lease, and template loading",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-room",
        "creation": "2026-05-24 21:04:00",
    },
    {
        "title": "v0.7.2: Arabic interface fully translated; broken translation lines repaired",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-24 21:05:00",
    },
    # v0.7.0 ---------------------------------------------------------------
    {
        "title": "Apex Habitat v0.7.0 — Security, Performance & Compliance Overhaul",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-05-24 10:00:00",
    },
    {
        "title": "v0.7.0: All 9 workspaces now restricted by role — no public desk access",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-24 10:01:00",
    },
    {
        "title": "v0.7.0: Bed booking now uses SELECT FOR UPDATE to prevent double-booking",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-assignment",
        "creation": "2026-05-24 10:02:00",
    },
    {
        "title": "v0.7.0: QR web form rate-limited to 5 requests/minute per IP",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-resident-request",
        "creation": "2026-05-24 10:03:00",
    },
    {
        "title": "v0.7.0: New DocType — Habitat Operations Alert (scheduler warnings now visible in desk)",
        "app_name": "apex_habitat",
        "link": "/app/habitat-operations-alert",
        "creation": "2026-05-24 10:04:00",
    },
    {
        "title": "v0.7.0: Scheduler pagination 500/batch — prevents timeouts on large data sets",
        "app_name": "apex_habitat",
        "link": "/app/habitat-settings",
        "creation": "2026-05-24 10:05:00",
    },
    {
        "title": "v0.7.0: Leap-year cost denominator fix — daily allocation now uses 365 or 366",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-ledger",
        "creation": "2026-05-24 10:06:00",
    },
    {
        "title": "v0.7.0: CI pipelines added — lint, test, and migrate-check on every push",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-24 10:07:00",
    },
    {
        "title": "v0.7.0: Room generator wizard — dynamic multi-row floor plan builder with 9 room types",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-05-24 10:08:00",
    },
    {
        "title": "v0.7.0: Accommodation Building supports Apartment type — floors auto-hidden for apartments",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-05-24 10:09:00",
    },
    {
        "title": "v0.7.0: DocType City added — 18 Saudi cities seeded, linked from Building and Site",
        "app_name": "apex_habitat",
        "link": "/app/city",
        "creation": "2026-05-24 10:10:00",
    },
    {
        "title": "v0.7.0: Inspection Finding consolidated — unified child table replaces 3 separate DocTypes",
        "app_name": "apex_habitat",
        "link": "/app/safety-inspection-report",
        "creation": "2026-05-24 10:11:00",
    },
    {
        "title": "v0.7.0: Generate Payment button on Accommodation Lease — supports Payment Entry, Payment Order, Expense Request",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-lease",
        "creation": "2026-05-24 10:12:00",
    },
    {
        "title": "v0.7.0: All controllers migrated to module-level hooks pattern per ADR",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-24 10:13:00",
    },
    # v0.6.0 ---------------------------------------------------------------
    {
        "title": "Apex Habitat v0.6.0 — Maintenance Materials & Database Cleanup",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-23 22:00:00",
    },
    {
        "title": "v0.6.0: Added Maintenance Material catalog (38 items) and 4 templates",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-23 22:01:00",
    },
    {
        "title": "v0.6.0: Added temporary database/workspace fresh-reload migration patch",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-23 22:02:00",
    },
    {
        "title": "v0.6.0: Added Generate Rooms/Beds and Safety Setup buttons on Accommodation Building form",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-05-23 22:03:00",
    },
    {
        "title": "Apex Habitat v0.5.0 — Building Safety Setup Generator",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-05-23 18:00:00",
    },
    {
        "title": "v0.5.0: Added Safety Setup generator method and 12 tracking fields on Building form",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-05-23 18:01:00",
    },
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
