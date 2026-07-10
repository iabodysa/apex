# Copyright (c) 2026, AFMCO and contributors
from frappe.utils import get_datetime

# [#l4tfhr]

_RELEASES = [
    {
        "title": "Apex 1.62.0 — housing and procurement staff can now confirm Asset Deliveries on-site: the Housing Portal has been fully wired into the app and now includes a dedicated Asset Delivery mobile interface; after the three exit checkpoints clear, the receiving supervisor enters the 6-digit on-site OTP directly from their phone to confirm receipt and securely log the asset transfer",
        "app_name": "apex",
        "link": "/housing",
        "creation": "2026-07-09 16:20:00",
    },
    {
        "title": "Apex 1.61.0 — workers can now rate their trips from the portal: a new 'Rate your trip' section appears on completed past trips in the Masar portal, letting workers give a 1-5 star rating and optional feedback that is recorded against the trip for fleet analytics",
        "app_name": "apex",
        "link": "/masar",
        "creation": "2026-07-09 16:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.67 — Seven Arabic labels and status words now read in their standard everyday business form.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-29 21:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.66 — More policy-picker help now reads in Arabic.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-29 20:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.65 — Loading placeholders show again on five operator Desk pages.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-29 19:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.64 — The Arrivals Desk, Custody Kiosk, and Fuel Approval Console look right again.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-29 18:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.63 — Policy pickers now carry a clear tooltip explaining each choice.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-29 17:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.62 — Deterministic module breadcrumbs plus field-label clarity fixes.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-29 16:00:00",
    },
    {
        "title": "Apex Habitat 1.60.61 — The worker's Home next-ride card now shows the live 'arriving in N min' ETA from the driver's GPS position, replacing the plain scheduled time when the driver is on the way",
        "app_name": "apex",
        "link": "/driver",
        "creation": "2026-06-29 15:00:00",
    },
    {
        "title": "Apex Habitat 1.60.60 — Workers see a live ETA for their next shuttle: the driver app shares its GPS position while a trip is under way, and the worker's Home shows how many minutes until the ride reaches their pickup",
        "app_name": "apex",
        "link": "/driver",
        "creation": "2026-06-29 14:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.59 — Arabic coverage for 52 previously-English labels, descriptions, and messages across freelance pay, salary-deduction authorization, data-retention settings, and fleet operations thresholds',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-29 13:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.58 — Safer data imports and a tighter safety-round check.',
        "app_name": "apex",
        "link": "/safety",
        "creation": "2026-06-29 12:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.56 — Security and reliability hardening: worker identity documents are scope-restricted, lookups are building-scoped, and night-shift trips stay visible across midnight.',
        "app_name": "apex",
        "link": "/masar",
        "creation": "2026-06-29 10:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.55 — You can now hand tracked assets over to accommodation with a checkpoint-controlled delivery.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-29 09:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.54 — Building leases now go through a submit-for-approval step before they take effect.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-29 08:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.53 — Portal frontend hardening: unified data fetching, resilient loading, upload consolidation, and PWA cleanup',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-29 07:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.52 — A robustness pass: clearer errors, faster lists, and steadier notifications.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-29 06:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.51 — The driver portal Home tab is back, and the header logo sits correctly.',
        "app_name": "apex",
        "link": "/driver",
        "creation": "2026-06-29 05:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.50 — Security hardening of the Masar worker access token.',
        "app_name": "apex",
        "link": "/masar",
        "creation": "2026-06-29 04:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.49 — Boarding self-confirm with driver exception override, a Salis Settings alert-aging section, and a setup wizard that configures all Apex settings.',
        "app_name": "apex",
        "link": "/driver",
        "creation": "2026-06-29 03:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.48 — Operational Desk boards now render with a clear, consistent visual style in both light and dark mode.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-29 02:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.47 — Lifecycle, controller, and DocType hygiene hardening across Habitat and Salis.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-29 01:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.46 — Portal fixes: driver-portal runtime error and the inventory-count surface for admins, plus Settings-consumer hardening',
        "app_name": "apex",
        "link": "/driver",
        "creation": "2026-06-29 00:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.45 — Workspaces restored to a parent/child sidebar hierarchy with runtime open-failures fixed.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 23:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.44 — Repair the workspace damage from the prior consolidation: re-home the finance domain, clean up orphans, and add per-workspace headline charts.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 22:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.43 — Freelance accounting party and a settings re-engineering pass: deduction policy consolidation, fleet authority gates, and Apex retention/payment/company controls.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 21:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.42 — Notification plumbing, Saudi National Address support, native bed-status colours, and an Arabic translation top-up.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 20:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.41 — Tighter guards on who can create records and approve movements.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 19:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.40 — Cleaner operator Desk pages and steadier workspaces.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 18:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.39 — The driver home logo keeps its shape.',
        "app_name": "apex",
        "link": "/driver",
        "creation": "2026-06-28 17:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.38 — Reliability fixes in asset movement and fuel handling.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 16:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.37 — Approvals now take effect, and each person sees only the records they are allowed to.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 15:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.36 — Stability improvements.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 14:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.35 — Steadier trip time checks and a clearer cost-recovery step.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 13:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.34 — Stability improvements.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 12:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.33 — Custody and transport screens that were erroring now load correctly.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 11:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.32 — Assign scheduled tasks to buildings more flexibly.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 10:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.31 — Daily cleaning logs and a gap-spotting audit report.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 09:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.30 — Guided setup for movement, plus tidier workspaces.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 08:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.29 — A simpler workspace layout.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 07:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.28 — Security scoping, validation guards, and workspace cleanup.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 06:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.27 — Accuracy fixes across custody balances, routes, and reports.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 05:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.26 — Housekeeping with no change to what you see.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 04:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.25 — A cleaner safety inspection form.',
        "app_name": "apex",
        "link": "/safety",
        "creation": "2026-06-28 03:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.24 — Accuracy fixes in request priority and work orders.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 02:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.23 — Data-integrity improvements in fuel and scheduled tasks.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 01:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.22 — Reusable route templates for faster scheduling.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-28 00:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.21 — Approvals for contracts and damages, plus a cleaning audit report.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-27 23:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.20 — Approvals now gate utility bills, leases, and deductions.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-27 22:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.19 — Internal naming cleanup with no change to what you see.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-27 21:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.18 — Clearer names, a tidier admin hub, and smarter fleet forms.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-27 20:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.17 — Work shifts and route assignments now flow through to trips.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-27 19:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.16 — A new lease form now fills in your company for you.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-27 18:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.15 — Security and reliability improvements in trips and routes.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-27 17:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.14 — Two more screens are now reachable from their workspaces.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-27 16:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.13 — Workspace polish and reliability improvements.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-27 15:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.12 — A mobile Housing Inventory count portal for field supervisors, and asset custody sign-off now moves the custodian.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-27 14:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.11 — Field-level permission hardening across DocTypes',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-27 13:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.10 — A new Creative portal theme, a driver-arrived signal for workers, ledger-backed cleaning compliance, and owner-scoped maintenance reports.',
        "app_name": "apex",
        "link": "/driver",
        "creation": "2026-06-27 12:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.9 — Rental Office now uses the native Address system (with a safe backfill); housing cleaning is now a daily system-of-record (auto-created cleaning logs).',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-27 11:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.8 — Per-worker boarding audit, scoped operations alerts, financial-control guards, cleaner desk + portal UI.',
        "app_name": "apex",
        "link": "/masar",
        "creation": "2026-06-27 10:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.7 — Added immutable posting ledgers so reports read fixed records that do not change retroactively.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-27 09:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.6 — Permission, validation, and data-integrity hardening across Movement and Habitat.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-27 08:00:00",
    },
    {
        "title": "Apex 1.60.5 — assign several transport requests onto one trip: a supervisor groups requests on a Dispatch Trip, the manifest is the union of their workers, a seat-capacity guard stops over-filling a vehicle, and each trip carries its purpose; several lists and reports now stay inside the building you can see, the public vehicle-incident and arrival-manifest forms are hardened against abuse, and a custody item's issued-to is now a proper user link, alongside reliability and layout tidy-ups",
        "app_name": "apex",
        "link": "/app/dispatch-trip",
        "creation": "2026-06-27 07:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.4 — You can now run a two-sided bus boarding and departure flow, with live confirmation between the driver and each rider.',
        "app_name": "apex",
        "link": "/driver",
        "creation": "2026-06-27 06:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.3 — Your driver and safety screens now update themselves, and the worker boarding pass shows just the trip a worker needs.',
        "app_name": "apex",
        "link": "/driver",
        "creation": "2026-06-27 05:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.2 — Fixes the four self-service portals showing their startup script as visible text instead of running it.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-27 04:00:00",
    },
    {
        "title": 'Apex Habitat 1.60.1 — Security hardening and reliability fixes across portals, fleet, custody and reports.',
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-27 03:00:00",
    },
    {
        "title": "Apex Habitat 1.60.0 — Keep a running count of what's in each building, and let drivers get a push even when the app is closed.",
        "app_name": "apex",
        "link": "/driver",
        "creation": "2026-06-27 02:00:00",
    },
    {
        "title": "Apex 1.59.1 — reliability fixes: driver hours, fuel allocation, rental returns and maintenance close-out now record accurately and stay in step across the two fleet screens; amounts, ledgers and who can approve are unchanged, and nothing already recorded is disturbed",
        "app_name": "apex",
        "link": "/driver",
        "creation": "2026-06-27 01:00:00",
    },
    {
        "title": "Apex 1.59 — drivers can board a trip even when a pass won't scan: the driver ticks each worker who got on from the trip's passenger list and confirms, so the boarded count stays in step (and re-confirming a worker changes nothing), each trip shows boarded against expected, and the driver checks off each stop as the route is completed; from Masar a worker opens the whole pickup route in Google Maps with every stop chained in order; from the arrivals screen you can send a worker their personal Masar link over WhatsApp or SMS in one tap (off until you set up a gateway in Settings, and it only sends a link the worker already has) and scan a passport to pre-fill the arrival details for you to check (opt-in, manual entry always stays); and the worker and driver apps now show a small banner when a new version is ready so a tap loads the latest",
        "app_name": "apex",
        "link": "/driver",
        "creation": "2026-06-27 00:30:00",
    },
    {
        "title": "Apex 1.58 — pickups now run by QR: a worker shows a boarding pass on their phone and the driver scans it from the app, so the boarded count and passenger list build themselves and any rider is one tap to call; a worker can request a ride for themselves and add unregistered co-travellers by name and ID; the fleet alert list becomes one you can work — take or assign an alert, snooze the ones that can wait, and see what is new since you last looked and what is overdue, with leaner filters; the worker app keeps showing its last saved information when the signal drops and now reads in Urdu, Hindi and Bengali too; and an optional Atelier theme plus a consistent desk style refine the look across portals and operator pages",
        "app_name": "apex",
        "link": "/app/operations-control",
        "creation": "2026-06-26 23:55:00",
    },
    {
        "title": "Apex 1.57 — drivers now run their whole day from a phone-friendly app: they install it to the home screen and keep working offline (a banner shows when saved data is on screen), snap a shift photo at check-in, open a trip or vehicle in Google Maps with one tap, follow a fuel request and its decision, and watch their license, clearance and vehicle-compliance dates before they lapse — and a driver is now notified about tomorrow's trip and about a fuel request decision, in the app and by their usual channel; a supervisor can register a new driver on the spot before assigning a vehicle and capture a vehicle handover during a reassignment as a draft the manager reviews; and every workspace is leaner, opening straight to the portal or screen you use most with a short curated set of shortcuts and counters instead of extra charts and lists, alongside a clearer first-time fleet setup",
        "app_name": "apex",
        "link": "/driver",
        "creation": "2026-06-26 23:30:00",
    },
    {
        "title": "Apex 1.56 — operations now move in real time: the Fleet Control and Operations Control boards update on their own as vehicles and alerts change, so trouble shows the moment it happens; arrivals, front desk, the custody kiosk and the driver app get a deep rework — residents tint by project so same-project workers group together, the bed board opens straight to your building, a worker badge or article barcode hands custody out by scan, and drivers reply to tickets, report a problem, start a trip and check document expiries from the app; a resident signs the housing terms at check-in and the signature is kept on the assignment; a guided custody go-live walks a new site through defining articles, issuing, returning and assessing damage; the worker app reads fully in Arabic (labels like Left and Suspended no longer leak English) with a developer-mode demo so the worker and driver apps are not empty on first look; and the What's-New note now appears once per version instead of replaying the whole history, alongside reliability work and tighter write-permission checks",
        "app_name": "apex",
        "link": "/app/operations-control",
        "creation": "2026-06-26 21:00:00",
    },
    {
        "title": "Apex 1.55 — the fleet board now keeps you ahead of trouble: a live alert bell shows the open-alert count updating on its own, and from its drawer you jump straight to the vehicle or the alert it belongs to; the board also stays usable when one data source hiccups (it shows the rest instead of going blank) and gains a per-vehicle timeline and clearer workshop status; a simple web form lets anyone report a fleet accident or theft for supervisor review before it takes effect; resident requests get a phone-friendly triage list that is colour-coded by priority, advances a request one tap at a time and can mark several as triaged at once; and custody now runs a daily check that flags held consumables past their usable life so they are replaced before they fail; plus reliability and Arabic-coverage improvements",
        "app_name": "apex",
        "link": "/fleet",
        "creation": "2026-06-26 18:00:00",
    },
    {
        "title": "Apex 1.54 — the Safety Checklist is reworked into a smarter, faster mobile screen at /safety: it shows only the rounds that are due right now (daily, weekly, monthly and so on appear automatically from what was last done, so no cadence is picked by hand), each task is checked with one tap (pass, fail or issue) plus an optional note and the whole visit is submitted in one step, and a report is then emailed to the manager (the recipient is configurable in Habitat Settings, otherwise the Accommodation Manager)",
        "app_name": "apex",
        "link": "/safety",
        "creation": "2026-06-18 16:00:00",
    },
    {
        "title": "Apex 1.53 — eight more core forms (Safety Inspection Report, Building License, Salis Vehicle, Salis Driver, Transport Request, Fuel Request, Rental Settlement) re-laid-out for clarity, completing the layout review of every core form; layout-only, no field or validation changed",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-11 12:00:00",
    },
    {
        "title": "Apex 1.52 — a deep correctness pass: facility asset movements now actually move the asset, rental accruals get reconciled and stamped by their settlement, blocked submittable documents can be cancelled again, negative payment and claim amounts are rejected, and resident requests convert into the right maintenance, safety or custody document",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-06-08 12:00:00",
    },
    {
        "title": "Apex 1.51 — Arrivals Desk floor fixes (Ground floor rooms group under Ground Floor, basements label correctly, only truly floor-less rooms stay Unassigned) and the noisy Unknown readiness state is hidden; check-in now falls back to the company's default cost center, and an overdue maintenance ticket now raises a desk-visible Operations Alert",
        "app_name": "apex",
        "link": "/app/arrivals-desk",
        "creation": "2026-06-05 21:00:00",
    },
    {
        "title": "Apex 1.50 — My Work is now a universal work center: pending approvals from any workflow, assigned tasks, notifications, and mentions all in one place inside the workspace",
        "app_name": "apex",
        "link": "/app/my-work",
        "creation": "2026-06-05 09:00:00",
    },
    {
        "title": "Apex 1.35 — a Unified Action Inbox: one screen of only the documents awaiting your action (workflow approvals + your tasks), with inline Approve/Reject and a nightly cleanup of stale rows",
        "app_name": "apex",
        "link": "/app/action-inbox",
        "creation": "2026-05-28 09:00:00",
    },
    {
        "title": "Apex 1.34 — the Arrivals Desk is reworked from desk feedback: native Frappe styling, a full-width three-column layout, a multi-item custody store, one group QR (no pop-up), and signed check-in / custody / arrival-card prints with an embedded QR",
        "app_name": "apex",
        "link": "/app/arrivals-desk",
        "creation": "2026-05-27 09:00:00",
    },
    {
        "title": "Apex 1.33 — the Arrivals Desk is rebuilt as one building-first screen: live floor-map, worker search, passport register, one-click housing (with over-capacity), custody, arrival card and multi-passenger transport",
        "app_name": "apex",
        "link": "/app/arrivals-desk",
        "creation": "2026-05-26 09:00:00",
    },
    {
        "title": "Apex 1.32 — a Temporary Worker auto-links to his Employee when HR registers the matching passport (housing/custody re-pointed, cost back-dated)",
        "app_name": "apex",
        "link": "/app/temporary-worker",
        "creation": "2026-05-25 09:00:00",
    },
    {
        "title": "Apex 1.31 — custody records (issue, return, damage) can now name a Temporary Worker too, like the housing records",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-05-24 09:00:00",
    },
    {
        "title": "Apex 1.30 — housing & worker records can now hold a passport-only Temporary Worker (pre-Iqama), with the Employee field kept in sync",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-05-23 09:00:00",
    },
    {
        "title": "Apex 1.29 — Native-first cleanups — the room-label print format now ships as a standard format (installs on new sites); the monthly rent-due reminder is now a native Frappe Notification on the unpaid schedule (replacing a custom scheduler); and the duplicated worker-link dialog (QR + WhatsApp) was consolidated from three desk scripts into one shared bundle.",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-05-22 12:00:00",
    },
    {
        "title": "Apex 1.28 — driver support tickets run on the native Issue desk with SLA",
        "app_name": "apex",
        "link": "/app/issue",
        "creation": "2026-05-21 09:00:00",
    },
    {
        "title": "Apex 1.27 — a one-screen Arrivals Desk for onboarding a worker",
        "app_name": "apex",
        "link": "/app/arrivals-desk",
        "creation": "2026-05-18 12:00:00",
    },
    {
        "title": "Apex 1.26 — Salis approvals run on native Frappe Workflow",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-05-17 09:01:00",
    },
    {
        "title": "Apex 1.25 — a formal safety-incident record with management escalation, and hardened worker links",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-05-13 09:02:00",
    },
    {
        "title": "Apex 1.24 — issuing a worker's Masar link is now easy, with a working QR and a WhatsApp share",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-05-12 09:02:00",
    },
    {
        "title": "Apex 1.23 — Masar becomes a complete worker self-service app",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-05-10 09:02:00",
    },
    {
        "title": "Apex 1.22 — the desk pages are more robust, dynamic, and comfortable",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-05-09 09:02:00",
    },
    {
        "title": "Apex 1.21 — a clean settings hub, KPI tiles on every Salis workspace, and a training guide",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-05-07 09:02:00",
    },
    {
        "title": "Apex 1.20 — driver portal: language toggle, profile and vehicle views",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-05-06 09:02:00",
    },
    {
        "title": "Apex 1.19 — Arabic module names, a tidier settings hub, and a cleaner portal",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-05-05 09:02:00",
    },
    {
        "title": "Apex 1.18 — driver portal check-ins now record attendance",
        "app_name": "apex",
        "link": "/app",
        "creation": "2026-05-03 09:02:00",
    },
    {
        "title": "Apex 1.17 — an integration kit so any frontend can use Apex as its backend",
        "app_name": "apex",
        "link": "/app/apex-core",
        "creation": "2026-04-28 09:02:00",
    },
    {
        "title": "Apex 1.16 — settings, console and Salis setup unified in one Apex Core workspace",
        "app_name": "apex",
        "link": "/app/apex-core",
        "creation": "2026-04-27 09:02:00",
    },
    {
        "title": "Apex 1.15 — shared settings get a dedicated Apex Core workspace",
        "app_name": "apex",
        "link": "/app/apex-core",
        "creation": "2026-04-26 09:02:00",
    },
    {
        "title": "Apex 1.14 — a refreshed, mobile-first driver portal and a cleaner fuel approval board",
        "app_name": "apex",
        "link": "/driver",
        "creation": "2026-04-25 09:02:00",
    },
    {
        "title": "Apex 1.13 — dispatch trips now run on a workflow, completing the Movement approval suite",
        "app_name": "apex",
        "link": "/app/dispatch-trip",
        "creation": "2026-04-22 09:02:00",
    },
    {
        "title": "Apex 1.12 — fuel claims and exception cases now run on guided approval workflows",
        "app_name": "apex",
        "link": "/app/fuel-claim",
        "creation": "2026-04-21 09:02:00",
    },
    {
        "title": "Apex 1.11 — fuel requests now run on a clear, role-based approval workflow",
        "app_name": "apex",
        "link": "/app/fuel-request",
        "creation": "2026-04-20 09:02:00",
    },
    {
        "title": "Apex 1.10 — fuel requests, top-ups and chip actions are now one screen",
        "app_name": "apex",
        "link": "/app/fuel-request",
        "creation": "2026-04-19 09:02:00",
    },
    {
        "title": "Apex 1.9 — the Driver Portal opens reliably for everyone",
        "app_name": "apex",
        "link": "/driver",
        "creation": "2026-04-18 09:02:00",
    },
    {
        "title": "Apex 1.8 — more Movement documents move on a real approval workflow",
        "app_name": "apex",
        "link": "/app/rental-settlement",
        "creation": "2026-04-16 09:02:00",
    },
    {
        "title": "Apex 1.7 — Transport Requests run on a real approval workflow, with sharper reports and sturdier engines",
        "app_name": "apex",
        "link": "/app/transport-request",
        "creation": "2026-04-15 09:03:00",
    },
    {
        "title": "Apex 1.6 — a focused desk that opens to your Apex areas",
        "app_name": "apex",
        "link": "/app/salis",
        "creation": "2026-04-14 09:00:00",
    },
    {
        "title": "Apex 1.5 — connected records everywhere, a Salis getting-started guide, and cleaner navigation",
        "app_name": "apex",
        "link": "/app/salis",
        "creation": "2026-04-12 09:04:00",
    },
    {
        "title": "Apex 1.4 — security & reliability improvements",
        "app_name": "apex",
        "link": "/app/salis",
        "creation": "2026-04-11 09:00:00",
    },
    {
        "title": "Apex 1.3 — quicker Salis navigation, one-tap record creation and a leaner role setup",
        "app_name": "apex",
        "link": "/app/salis",
        "creation": "2026-04-09 09:03:00",
    },
    {
        "title": "Apex 1.2 — Salis gets a live dispatch board, deeper dashboards, printable documents and smarter alerts",
        "app_name": "apex",
        "link": "/app/salis",
        "creation": "2026-04-08 09:05:00",
    },
    {
        "title": "Apex 1.1 — security & reliability improvements",
        "app_name": "apex",
        "link": "/app/salis",
        "creation": "2026-04-07 09:00:00",
    },
    {
        "title": "Apex 1.0 — security & reliability improvements",
        "app_name": "apex",
        "link": "/driver",
        "creation": "2026-04-05 09:00:00",
    },
    {
        "title": "Apex Habitat 0.9 — guided setup is back, and every record shows what it's connected to",
        "app_name": "apex",
        "link": "/app/apex-core",
        "creation": "2026-04-01 09:32:00",
    },
    {
        "title": "Apex Habitat 0.8 — check residents in and out from a visual board, and never lose track of an idle worker",
        "app_name": "apex",
        "link": "/app/front-desk",
        "creation": "2026-03-21 09:03:00",
    },
    {
        "title": "Apex Habitat 0.7 — faster reports, a fully translated interface, and security & reliability improvements",
        "app_name": "apex",
        "link": "/app/apex-core",
        "creation": "2026-03-19 21:05:00",
    },
    {
        "title": "Apex Habitat 0.6 — stock your maintenance catalog and set up a building from one screen",
        "app_name": "apex",
        "link": "/app/apex-core",
        "creation": "2026-03-18 22:03:00",
    },
    {
        "title": "Apex Habitat 0.5 — give every building a safety checklist in one tap",
        "app_name": "apex",
        "link": "/app/building",
        "creation": "2026-03-18 18:01:00",
    },
    {
        "title": "Apex Habitat 0.4 — set up accommodation in bulk and get every room ready",
        "app_name": "apex",
        "link": "/app/building",
        "creation": "2026-03-18 00:03:00",
    },
    {
        "title": "Apex 0.3 — Track assets moving between companies, and jump to any report from eight new shortcuts",
        "app_name": "apex",
        "link": "/app/facility-asset-movement",
        "creation": "2026-03-15 00:00:00",
    },
]


# [#a0cv0f]
_FEED_TITLE_MAX = 140

# Cap on how many items the sidebar "What's New" bell surfaces in one pull. `_RELEASES`
# is kept COMPLETE on purpose (the TestFeedCoversPopups contract asserts every shipped
# popup version has a source entry), but a user with an old/empty `since` must not be
# dumped the entire multi-year back-catalogue. `_RELEASES` is newest-first, so slicing
# the filtered result keeps the most recent releases. Bounded surface, complete source.
_FEED_MAX = 20


def _clip_title(title):
    title = title.strip()
    if len(title) <= _FEED_TITLE_MAX:
        return title
    return title[: _FEED_TITLE_MAX - 1].rstrip() + "…"


def get_changelog_feed(since):
    """
    Returns Apex Habitat release items newer than `since`, newest first, capped at
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
