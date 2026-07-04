# Copyright (c) 2026, AFMCO and contributors
from frappe.utils import get_datetime

# [#l4tfhr]

_RELEASES = [
    {
        "title": "Apex 1.60.58 — logistics importer and safety round security hardening: driver and vehicle data imports now support update-on-exists logic; the safety round checklist single submission write path is secured with building read permission validation, alongside automated test coverage for imports and checklist API gating",
        "app_name": "apex_habitat",
        "link": "/safety",
        "creation": "2026-06-29 12:00:00",
    },
    {
        "title": "Apex 1.60.5 — assign several transport requests onto one trip: a supervisor groups requests on a Dispatch Trip, the manifest is the union of their workers, a seat-capacity guard stops over-filling a vehicle, and each trip carries its purpose; several lists and reports now stay inside the building you can see, the public vehicle-incident and arrival-manifest forms are hardened against abuse, and a custody item's issued-to is now a proper user link, alongside reliability and layout tidy-ups",
        "app_name": "apex_habitat",
        "link": "/app/dispatch-trip",
        "creation": "2026-06-27 12:00:00",
    },
    {
        "title": "Apex 1.60.3 — your driver and safety screens now update themselves: the driver and safety apps refresh on their own the moment a trip or safety round changes, and the worker portal quietly refreshes while it is the screen you are looking at; the worker boarding pass is redesigned as a themed ticket that shows the worker only their own pickup and destination instead of the full driver route; opening a stop in Maps now drops you on the real place, trip cards fit small phone screens, safety reports are grouped into five clear sections, and more of the app reads correctly in Arabic",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-06-27 03:00:00",
    },
    {
        "title": "Apex 1.60 — keep a running count of what's in each building: a new housing inventory register tracks countable items (furniture, appliances, linen, kitchenware) per building and room, with expected against counted quantity, the variance, and each item's condition, and a completed maintenance work order on a linked item updates the matching row on its own (the maintenance date moves forward and a needs-maintenance flag clears) so nothing is re-keyed by hand; and a driver can opt in on their own device to receive background notifications, so a trip assignment or a fuel decision reaches them even when the app is closed (off until you turn it on and set it up in Settings, with nothing sent until then)",
        "app_name": "apex_habitat",
        "link": "/app/housing-inventory",
        "creation": "2026-06-27 02:00:00",
    },
    {
        "title": "Apex 1.59.1 — reliability fixes: driver hours, fuel allocation, rental returns and maintenance close-out now record accurately and stay in step across the two fleet screens; amounts, ledgers and who can approve are unchanged, and nothing already recorded is disturbed",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-06-27 01:00:00",
    },
    {
        "title": "Apex 1.59 — drivers can board a trip even when a pass won't scan: the driver ticks each worker who got on from the trip's passenger list and confirms, so the boarded count stays in step (and re-confirming a worker changes nothing), each trip shows boarded against expected, and the driver checks off each stop as the route is completed; from Masar a worker opens the whole pickup route in Google Maps with every stop chained in order; from the arrivals screen you can send a worker their personal Masar link over WhatsApp or SMS in one tap (off until you set up a gateway in Settings, and it only sends a link the worker already has) and scan a passport to pre-fill the arrival details for you to check (opt-in, manual entry always stays); and the worker and driver apps now show a small banner when a new version is ready so a tap loads the latest",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-06-27 00:30:00",
    },
    {
        "title": "Apex 1.58 — pickups now run by QR: a worker shows a boarding pass on their phone and the driver scans it from the app, so the boarded count and passenger list build themselves and any rider is one tap to call; a worker can request a ride for themselves and add unregistered co-travellers by name and ID; the fleet alert list becomes one you can work — take or assign an alert, snooze the ones that can wait, and see what is new since you last looked and what is overdue, with leaner filters; the worker app keeps showing its last saved information when the signal drops and now reads in Urdu, Hindi and Bengali too; and an optional Atelier theme plus a consistent desk style refine the look across portals and operator pages",
        "app_name": "apex_habitat",
        "link": "/app/operations-control",
        "creation": "2026-06-26 23:55:00",
    },
    {
        "title": "Apex 1.57 — drivers now run their whole day from a phone-friendly app: they install it to the home screen and keep working offline (a banner shows when saved data is on screen), snap a shift photo at check-in, open a trip or vehicle in Google Maps with one tap, follow a fuel request and its decision, and watch their license, clearance and vehicle-compliance dates before they lapse — and a driver is now notified about tomorrow's trip and about a fuel request decision, in the app and by their usual channel; a supervisor can register a new driver on the spot before assigning a vehicle and capture a vehicle handover during a reassignment as a draft the manager reviews; and every workspace is leaner, opening straight to the portal or screen you use most with a short curated set of shortcuts and counters instead of extra charts and lists, alongside a clearer first-time fleet setup",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-06-26 23:30:00",
    },
    {
        "title": "Apex 1.56 — operations now move in real time: the Fleet Control and Operations Control boards update on their own as vehicles and alerts change, so trouble shows the moment it happens; arrivals, front desk, the custody kiosk and the driver app get a deep rework — residents tint by project so same-project workers group together, the bed board opens straight to your building, a worker badge or article barcode hands custody out by scan, and drivers reply to tickets, report a problem, start a trip and check document expiries from the app; a resident signs the housing terms at check-in and the signature is kept on the assignment; a guided custody go-live walks a new site through defining articles, issuing, returning and assessing damage; the worker app reads fully in Arabic (labels like Left and Suspended no longer leak English) with a developer-mode demo so the worker and driver apps are not empty on first look; and the What's-New note now appears once per version instead of replaying the whole history, alongside reliability work and tighter write-permission checks",
        "app_name": "apex_habitat",
        "link": "/app/operations-control",
        "creation": "2026-06-26 21:00:00",
    },
    {
        "title": "Apex 1.55 — the fleet board now keeps you ahead of trouble: a live alert bell shows the open-alert count updating on its own, and from its drawer you jump straight to the vehicle or the alert it belongs to; the board also stays usable when one data source hiccups (it shows the rest instead of going blank) and gains a per-vehicle timeline and clearer workshop status; a simple web form lets anyone report a fleet accident or theft for supervisor review before it takes effect; resident requests get a phone-friendly triage list that is colour-coded by priority, advances a request one tap at a time and can mark several as triaged at once; and custody now runs a daily check that flags held consumables past their usable life so they are replaced before they fail; plus reliability and Arabic-coverage improvements",
        "app_name": "apex_habitat",
        "link": "/fleet",
        "creation": "2026-06-26 18:00:00",
    },
    {
        "title": "Apex 1.54 — the Safety Checklist is reworked into a smarter, faster mobile screen at /safety: it shows only the rounds that are due right now (daily, weekly, monthly and so on appear automatically from what was last done, so no cadence is picked by hand), each task is checked with one tap (pass, fail or issue) plus an optional note and the whole visit is submitted in one step, and a report is then emailed to the manager (the recipient is configurable in Habitat Settings, otherwise the Accommodation Manager)",
        "app_name": "apex_habitat",
        "link": "/safety",
        "creation": "2026-06-18 16:00:00",
    },
    {
        "title": "Apex 1.53 — eight more core forms (Safety Inspection Report, Building License, Salis Vehicle, Salis Driver, Transport Request, Fuel Request, Rental Settlement) re-laid-out for clarity, completing the layout review of every core form; layout-only, no field or validation changed",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-06-11 12:00:00",
    },
    {
        "title": "Apex 1.52 — a deep correctness pass: facility asset movements now actually move the asset, rental accruals get reconciled and stamped by their settlement, blocked submittable documents can be cancelled again, negative payment and claim amounts are rejected, and resident requests convert into the right maintenance, safety or custody document",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-06-08 12:00:00",
    },
    {
        "title": "Apex 1.51 — Arrivals Desk floor fixes (Ground floor rooms group under Ground Floor, basements label correctly, only truly floor-less rooms stay Unassigned) and the noisy Unknown readiness state is hidden; check-in now falls back to the company's default cost center, and an overdue maintenance ticket now raises a desk-visible Operations Alert",
        "app_name": "apex_habitat",
        "link": "/app/arrivals-desk",
        "creation": "2026-06-05 21:00:00",
    },
    {
        "title": "Apex 1.50 — My Work is now a universal work center: pending approvals from any workflow, assigned tasks, notifications, and mentions all in one place inside the workspace",
        "app_name": "apex_habitat",
        "link": "/app/my-work",
        "creation": "2026-06-05 09:00:00",
    },
    {
        "title": "Apex 1.35 — a Unified Action Inbox: one screen of only the documents awaiting your action (workflow approvals + your tasks), with inline Approve/Reject and a nightly cleanup of stale rows",
        "app_name": "apex_habitat",
        "link": "/app/action-inbox",
        "creation": "2026-05-28 09:00:00",
    },
    {
        "title": "Apex 1.34 — the Arrivals Desk is reworked from desk feedback: native Frappe styling, a full-width three-column layout, a multi-item custody store, one group QR (no pop-up), and signed check-in / custody / arrival-card prints with an embedded QR",
        "app_name": "apex_habitat",
        "link": "/app/arrivals-desk",
        "creation": "2026-05-27 09:00:00",
    },
    {
        "title": "Apex 1.33 — the Arrivals Desk is rebuilt as one building-first screen: live floor-map, worker search, passport register, one-click housing (with over-capacity), custody, arrival card and multi-passenger transport",
        "app_name": "apex_habitat",
        "link": "/app/arrivals-desk",
        "creation": "2026-05-26 09:00:00",
    },
    {
        "title": "Apex 1.32 — a Temporary Worker auto-links to his Employee when HR registers the matching passport (housing/custody re-pointed, cost back-dated)",
        "app_name": "apex_habitat",
        "link": "/app/temporary-worker",
        "creation": "2026-05-25 09:00:00",
    },
    {
        "title": "Apex 1.31 — custody records (issue, return, damage) can now name a Temporary Worker too, like the housing records",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-24 09:00:00",
    },
    {
        "title": "Apex 1.30 — housing & worker records can now hold a passport-only Temporary Worker (pre-Iqama), with the Employee field kept in sync",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-23 09:00:00",
    },
    {
        "title": "Apex 1.29 — Native-first cleanups — the room-label print format now ships as a standard format (installs on new sites); the monthly rent-due reminder is now a native Frappe Notification on the unpaid schedule (replacing a custom scheduler); and the duplicated worker-link dialog (QR + WhatsApp) was consolidated from three desk scripts into one shared bundle.",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-22 12:00:00",
    },
    {
        "title": "Apex 1.28 — driver support tickets run on the native Issue desk with SLA",
        "app_name": "apex_habitat",
        "link": "/app/issue",
        "creation": "2026-05-21 09:00:00",
    },
    {
        "title": "Apex 1.27 — a one-screen Arrivals Desk for onboarding a worker",
        "app_name": "apex_habitat",
        "link": "/app/arrivals-desk",
        "creation": "2026-05-18 12:00:00",
    },
    {
        "title": "Apex 1.26 — Salis approvals run on native Frappe Workflow",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-17 09:01:00",
    },
    {
        "title": "Apex 1.25 — a formal safety-incident record with management escalation, and hardened worker links",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-13 09:02:00",
    },
    {
        "title": "Apex 1.24 — issuing a worker's Masar link is now easy, with a working QR and a WhatsApp share",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-12 09:02:00",
    },
    {
        "title": "Apex 1.23 — Masar becomes a complete worker self-service app",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-10 09:02:00",
    },
    {
        "title": "Apex 1.22 — the desk pages are more robust, dynamic, and comfortable",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-09 09:02:00",
    },
    {
        "title": "Apex 1.21 — a clean settings hub, KPI tiles on every Salis workspace, and a training guide",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-07 09:02:00",
    },
    {
        "title": "Apex 1.20 — driver portal: language toggle, profile and vehicle views",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-06 09:02:00",
    },
    {
        "title": "Apex 1.19 — Arabic module names, a tidier settings hub, and a cleaner portal",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-05 09:02:00",
    },
    {
        "title": "Apex 1.18 — driver portal check-ins now record attendance",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-03 09:02:00",
    },
    {
        "title": "Apex 1.17 — an integration kit so any frontend can use Apex as its backend",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-04-28 09:02:00",
    },
    {
        "title": "Apex 1.16 — settings, console and Salis setup unified in one Apex Core workspace",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-04-27 09:02:00",
    },
    {
        "title": "Apex 1.15 — shared settings get a dedicated Apex Core workspace",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-04-26 09:02:00",
    },
    {
        "title": "Apex 1.14 — a refreshed, mobile-first driver portal and a cleaner fuel approval board",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-04-25 09:02:00",
    },
    {
        "title": "Apex 1.13 — dispatch trips now run on a workflow, completing the Movement approval suite",
        "app_name": "apex_habitat",
        "link": "/app/dispatch-trip",
        "creation": "2026-04-22 09:02:00",
    },
    {
        "title": "Apex 1.12 — fuel claims and exception cases now run on guided approval workflows",
        "app_name": "apex_habitat",
        "link": "/app/fuel-claim",
        "creation": "2026-04-21 09:02:00",
    },
    {
        "title": "Apex 1.11 — fuel requests now run on a clear, role-based approval workflow",
        "app_name": "apex_habitat",
        "link": "/app/fuel-request",
        "creation": "2026-04-20 09:02:00",
    },
    {
        "title": "Apex 1.10 — fuel requests, top-ups and chip actions are now one screen",
        "app_name": "apex_habitat",
        "link": "/app/fuel-request",
        "creation": "2026-04-19 09:02:00",
    },
    {
        "title": "Apex 1.9 — the Driver Portal opens reliably for everyone",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-04-18 09:02:00",
    },
    {
        "title": "Apex 1.8 — more Movement documents move on a real approval workflow",
        "app_name": "apex_habitat",
        "link": "/app/rental-settlement",
        "creation": "2026-04-16 09:02:00",
    },
    {
        "title": "Apex 1.7 — Transport Requests run on a real approval workflow, with sharper reports and sturdier engines",
        "app_name": "apex_habitat",
        "link": "/app/transport-request",
        "creation": "2026-04-15 09:03:00",
    },
    {
        "title": "Apex 1.6 — a focused desk that opens to your Apex areas",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-14 09:00:00",
    },
    {
        "title": "Apex 1.5 — connected records everywhere, a Salis getting-started guide, and cleaner navigation",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-12 09:04:00",
    },
    {
        "title": "Apex 1.4 — security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-11 09:00:00",
    },
    {
        "title": "Apex 1.3 — quicker Salis navigation, one-tap record creation and a leaner role setup",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-09 09:03:00",
    },
    {
        "title": "Apex 1.2 — Salis gets a live dispatch board, deeper dashboards, printable documents and smarter alerts",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-08 09:05:00",
    },
    {
        "title": "Apex 1.1 — security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-07 09:00:00",
    },
    {
        "title": "Apex 1.0 — security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-04-05 09:00:00",
    },
    {
        "title": "Apex Habitat 0.9 — guided setup is back, and every record shows what it's connected to",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-04-01 09:32:00",
    },
    {
        "title": "Apex Habitat 0.8 — check residents in and out from a visual board, and never lose track of an idle worker",
        "app_name": "apex_habitat",
        "link": "/app/front-desk",
        "creation": "2026-03-21 09:03:00",
    },
    {
        "title": "Apex Habitat 0.7 — faster reports, a fully translated interface, and security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-03-19 21:05:00",
    },
    {
        "title": "Apex Habitat 0.6 — stock your maintenance catalog and set up a building from one screen",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-03-18 22:03:00",
    },
    {
        "title": "Apex Habitat 0.5 — give every building a safety checklist in one tap",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-03-18 18:01:00",
    },
    {
        "title": "Apex Habitat 0.4 — set up accommodation in bulk and get every room ready",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-03-18 00:03:00",
    },
    {
        "title": "Apex 0.3 — Track assets moving between companies, and jump to any report from eight new shortcuts",
        "app_name": "apex_habitat",
        "link": "/app/facility-asset-movement",
        "creation": "2026-03-15 00:00:00",
    },
]


# [#a0cv0f]
_FEED_TITLE_MAX = 140


def _clip_title(title):
    title = title.strip()
    if len(title) <= _FEED_TITLE_MAX:
        return title
    return title[: _FEED_TITLE_MAX - 1].rstrip() + "…"


def get_changelog_feed(since):
    """
    Returns Apex Habitat release items newer than `since`.
    Registered via hooks.py get_changelog_feed hook.
    Frappe's fetch_changelog_feed() calls this and deduplicates by exact field match.
    """
    since_dt = get_datetime(since)
    return [
        {**r, "title": _clip_title(r["title"])}
        for r in _RELEASES
        if get_datetime(r["creation"]) > since_dt
    ]
