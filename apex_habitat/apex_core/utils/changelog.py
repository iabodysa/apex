from frappe.utils import get_datetime

# [#l4tfhr]

_RELEASES = [
    {
        "title": "Apex 1.55.28 — completing a Final Exit or End of Contract resident check-out now offers a one-click Arrange Departure Transport button that raises the relocation transport for that worker and links it back to the check-out (idempotent — asking twice reuses the same request); drivers now get in-app alerts when their own clearance is blocked or their vehicle's compliance is expiring soon; the Fleet Control board's Export CSV now builds the file on the server from the current filters so it holds every vehicle you are permitted to see rather than only the painted rows; the pre-arrival manifest (Arrival Batch) gains its own link on the Housing workspace; and the Front Desk bed board now mirrors cleanly right-to-left in Arabic",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-checkout",
        "creation": "2026-06-25 16:00:00",
    },
    {
        "title": "Apex 1.55.27 — labour suppliers can submit a pre-arrival manifest from a public web form (the workers expected at a building on a date, which the accommodation team prepares beds for and reconciles arrivals against); reassigning a vehicle now picks the new driver from a verified, permitted list instead of a free-typed id, so a typo can no longer silently mis-assign; supervisors get a daily digest of their open operations alerts grouped by severity; the operations control board adds compliance-at-risk and stopped-over-threshold counts to its summary; and notification delivery is hardened so enabled alerts send dependably",
        "app_name": "apex_habitat",
        "link": "/arrival-manifest",
        "creation": "2026-06-25 12:00:00",
    },
    {
        "title": "Apex 1.54.29 — the Safety Checklist is reworked into a smarter, faster mobile screen at /safety: it shows only the rounds that are due right now (daily, weekly, monthly and so on appear automatically from what was last done, so no cadence is picked by hand), each task is checked with one tap (pass, fail or issue) plus an optional note and the whole visit is submitted in one step, and a report is then emailed to the manager (the recipient is configurable in Habitat Settings, otherwise the Accommodation Manager)",
        "app_name": "apex_habitat",
        "link": "/safety",
        "creation": "2026-06-18 16:00:00",
    },
    {
        "title": "Apex 1.54.28 — a new Safety Checklist desk page lets a supervisor pick a building and a cadence, tick off that cadence's safety tasks, and submit the whole round in one step (recording the round and each task result together and showing the overall result); it is open to the roles that can sign off a round and is linked from the Safety workspace; and the old Safety Inspection Report is now fully retired from the desk — its number card and trend chart read the new Safety Rounds and the safety onboarding step opens the new page",
        "app_name": "apex_habitat",
        "link": "/app/safety-checklist",
        "creation": "2026-06-18 15:00:00",
    },
    {
        "title": "Apex 1.54.27 — a new Safety Round groups a building's safety-task checks for one cadence (daily, weekly, monthly, quarterly or annual) into one submittable round that derives a Pass / Needs Attention / Fail result, with a Safety Round Compliance report showing per task what still needs attention; the old Safety Inspection Report is retired in place (hidden and read-only, its records kept); and the Fleet dashboard now uses a clean professional Lucide icon set instead of emoji",
        "app_name": "apex_habitat",
        "link": "/app/safety-round",
        "creation": "2026-06-18 14:00:00",
    },
    {
        "title": "Apex 1.54.26 — Accommodation Buildings that had an address recorded before the dedicated Building Address field now display it on the form automatically instead of falling back to the site's address; the one-time fill-in never overwrites a building that already has a Building Address, and leaves address-less buildings unchanged",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-06-18 13:00:00",
    },
    {
        "title": "Apex 1.54.25 — assigning a building's Responsible Facility Supervisor now automatically scopes that supervisor's access to the building (the matching User Permission is created, moved, or removed to follow the field), so building access tracks the supervisor field instead of a separately-maintained permission",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-06-18 10:00:00",
    },
    {
        "title": "Apex 1.54.24 — the Accommodation Building form now has a Building Address field you can select; when set, the building's own address is shown instead of the Accommodation Site's, and the display updates the moment you change it",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-06-18 09:30:00",
    },
    {
        "title": "Apex 1.54.23 — on the Accommodation Building form, switching the Site now immediately shows that site's address; it used to keep displaying the previously-saved site's address until you saved and reloaded",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-06-17 18:00:00",
    },
    {
        "title": "Apex 1.54.22 — the driver portal's trip cards now show the vehicle plate number and route name instead of the internal record ids (VEH-…, RP-…) that used to appear",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-06-17 17:00:00",
    },
    {
        "title": "Apex 1.54.21 — a worker who raises a housing request while having no active accommodation assignment no longer sees an English note inside their Arabic request: the orphaned-context signal is now a structured, translatable No Active Assignment flag on the request (which supervisors can filter) instead of free English text spliced into the description",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-resident-request",
        "creation": "2026-06-17 16:30:00",
    },
    {
        "title": "Apex 1.54.20 — eight more Habitat desk strings now render in Arabic (the arrivals-desk action counters, the room-setup floor summary, and the maintenance template material-load message), and the Arabic-coverage guard test now spans the whole app's desk and www surfaces instead of only the fleet pages",
        "app_name": "apex_habitat",
        "link": "/app/arrivals-desk",
        "creation": "2026-06-17 15:00:00",
    },
    {
        "title": "Apex 1.54.19 — the Fleet Control page and several fleet and housing surfaces no longer leak English into the Arabic interface: 55 status, alert and action strings (including the Fleet Control export-count and open-incident labels) are now translated, and a guard test fails the build if any fleet desk page or the /fleet portal adds a translate-call string without an Arabic entry",
        "app_name": "apex_habitat",
        "link": "/app/operations-control",
        "creation": "2026-06-17 09:00:00",
    },
    {
        "title": "Apex 1.54.18 — Salis Settings gains two alert windows the code already read but the form was missing: Workshop Overstay Days (default 14) and License Alert Lead Days (default 30), so the Maintenance Overdue and licence-expiry alerts are configurable instead of stuck at their hard defaults",
        "app_name": "apex_habitat",
        "link": "/app/salis-settings",
        "creation": "2026-06-16 14:30:00",
    },
    # [#ma8w6v]
    {
        "title": "Apex 1.54.17 — a Fleet dashboard reassignment fix from a security audit: reassigning a driver now fully succeeds or makes no change. If a concurrent reassignment wins the race, the second is rejected cleanly instead of silently overwriting the vehicle's live driver and leaving an unsubmitted assignment behind",
        "app_name": "apex_habitat",
        "link": "/fleet",
        "creation": "2026-06-16 13:00:00",
    },
    # [#4o9hya]
    {
        "title": "Apex 1.54.16 — Fleet Operations gets a Workshop Overstay number card (counts vehicles still in the workshop past the overstay cutoff, the same rule as the Maintenance Overdue alert, scoped to your permitted projects), and the Operations Control page's vehicle drawer gains quick actions that open a new Vehicle Stop, Vehicle Incident or Vehicle Assignment prefilled for the selected vehicle",
        "app_name": "apex_habitat",
        "link": "/app/fleet-operations",
        "creation": "2026-06-16 12:30:00",
    },
    # [#ek8ntq]
    {
        "title": "Apex 1.54.15 — the /fleet dashboard is rebuilt as a Vue single-page app (the fleet_portal portal, like /driver and /masar) while keeping the supervisor's exact board design; it reads and writes the same live Salis DocTypes through the same permission-gated API, drops the obsolete version/date line and the dead save and export buttons, adds loading, empty and error states plus a keyboard focus ring and a reduced-motion option, and shows a signed-in user without a fleet role a friendly notice instead of a raw error",
        "app_name": "apex_habitat",
        "link": "/fleet",
        "creation": "2026-06-16 11:00:00",
    },
    # [#okzano]
    {
        "title": "Apex 1.54.14 — security hardening for the Fleet dashboard from a skeptics audit: driver phone and external id (permlevel-1 fields) are now hidden from roles not granted them (Fleet Supervisor / Fleet Project Manager see names, not contact details) on both the Fleet dashboard and the Dispatch Board; reassigning a driver now permission-checks the driver as well as the vehicle and stamps the assignment's project, so a project-scoped supervisor cannot pair an out-of-scope driver to a vehicle",
        "app_name": "apex_habitat",
        "link": "/fleet",
        "creation": "2026-06-16 10:00:00",
    },
    # [#qygvuh]
    {
        "title": "Apex 1.54.13 — fix the Fleet dashboard cards failing to render: the /fleet board threw a script error and showed no vehicles because the API sent a vehicle's current driver as a partial record missing the project and date fields the card reads; the API now returns the current driver in the same full shape as a custody-history entry, so every card and detail panel renders",
        "app_name": "apex_habitat",
        "link": "/fleet",
        "creation": "2026-06-16 09:30:00",
    },
    # [#a5lrbn]
    {
        "title": "Apex 1.54.12 — a new /fleet web dashboard serves the fleet supervisor's exact board design, but every vehicle, driver and custody record reads live from the Salis DocTypes, and its actions (reassign, stop, workshop in/out, recover, report theft) update the real records; it is open to logged-in fleet roles only, and the obsolete Save/Export buttons are gone now that the data lives in Apex",
        "app_name": "apex_habitat",
        "link": "/fleet",
        "creation": "2026-06-15 19:30:00",
    },
    # [#l66z1p]
    {
        "title": "Apex 1.54.11 — more Fleet Operations: an Operating Days trend and a Vehicle Activations trend chart on the workspace, Vehicle Stop now records workshop-exit details (return date, released on/by, estimated cost) to close out a maintenance stop, and Salis Settings gains reference fuel prices (Petrol 91/95, Diesel) for budgeting",
        "app_name": "apex_habitat",
        "link": "/app/fleet-operations",
        "creation": "2026-06-15 17:00:00",
    },
    # [#r664e3]
    {
        "title": "Apex 1.54.10 — Fleet Operations workspace fixes: the Fleet Control page now shows as a shortcut on the workspace (a stale timestamp had blocked it from syncing on migrate), and the workspace icons are de-duplicated so the Salis hub and Fleet Operations no longer share the Fleet wrench icon",
        "app_name": "apex_habitat",
        "link": "/app/fleet-operations",
        "creation": "2026-06-15 16:30:00",
    },
    # [#37rhxh]
    {
        "title": "Apex 1.54.9 — the worker-transport workspace is now named Masar and opens at /app/masar (it was named Movement but labelled Masar, so navigating to Masar returned a page-not-found); a migration renames the workspace on existing sites and no content changes",
        "app_name": "apex_habitat",
        "link": "/app/masar",
        "creation": "2026-06-15 15:00:00",
    },
    # [#7ohwq5]
    {
        "title": "Apex 1.54.8 — a new Fleet Control desk page (under Fleet Operations) gives a live, filterable vehicle board: every vehicle as a status-coloured card or table, filters for status/office/project and a plate search, a per-vehicle detail drawer (driver, compliance, recent incidents and custody assignments), and a CSV export of the current view",
        "app_name": "apex_habitat",
        "link": "/app/operations-control",
        "creation": "2026-06-15 12:00:00",
    },
    # [#hnqwk1]
    {
        "title": "Apex 1.54.7 — a new Fleet Operations workspace brings the day-to-day fleet control surface together: live fleet metrics (now including open vehicle incidents and open theft reports), an Incidents-by-Type chart, an open-incident quick list, and grouped links for incidents, vehicle custody and office billing",
        "app_name": "apex_habitat",
        "link": "/app/fleet-operations",
        "creation": "2026-06-15 09:00:00",
    },
    # [#izigzh]
    {
        "title": "Apex 1.54.6 — foundations for Fleet Operations: a new Vehicle Incident record captures accident and theft events against a vehicle (location, police report number, fault, evidence), and submitting a theft takes the vehicle out of service and clears its driver (cancelling restores both); a damage write-off can now be linked back to the incident it was escalated from and carries the damaged parts and reporter; and vehicles gain an optional planned fuel grade and daily fuel budget while drivers carry a unique fleet identifier used as the data-import key",
        "app_name": "apex_habitat",
        "link": "/app/vehicle-incident",
        "creation": "2026-06-15 06:00:00",
    },
    # [#6djm8h]
    {
        "title": "Apex 1.54.5 — closes a finance-approval bypass in payment routing: a request is now treated as finance-approved only by the server-stamped approver recorded by the finance-approval step (after the finance-role and segregation-of-duties checks), never by the editable status field; and that approver stamp is server-owned, so it can no longer be forged when a request is created or edited. A real payment can no longer be routed for a request that did not actually clear finance",
        "app_name": "apex_habitat",
        "link": "/app/salis-payment-request",
        "creation": "2026-06-14 12:00:00",
    },
    # [#hmiwwt]
    {
        "title": "Apex 1.54.4 — critical security and capacity fixes: routed-payment creation is now serialized with a row-lock, so two concurrent requests can no longer create a duplicate payment or a double ledger post; the routed-payment permission gate moved to the chokepoint, so every caller (including any future direct caller) is authorized before the payment is built; and a building's Total Bed Capacity now derives from its actual physical beds (excluding out-of-service and virtual over-capacity beds) and is read-only, so occupancy, cost-per-capacity and over-capacity figures can no longer drift",
        "app_name": "apex_habitat",
        "link": "/app/salis-payment-request",
        "creation": "2026-06-14 06:00:00",
    },
    # [#bjnt5l]
    {
        "title": "Apex 1.54.3 — worker-portal (Masar) fixes: the bottom Accommodation tab is now labeled and highlighted correctly (the landing tab no longer stays lit on every screen); a revoked, expired, or rate-limited session shows a clear error with retry instead of a misleading empty state; status, request-type, category and priority values render in Arabic in the Arabic interface; plus the Arabic web font, international WhatsApp links, a larger language-toggle tap target, and navigation polish",
        "app_name": "apex_habitat",
        "link": "/masar",
        "creation": "2026-06-13 18:00:00",
    },
    # [#9l3l5v]
    {
        "title": "Apex 1.54.2 — the routed-payment endpoint now rechecks source write and submit permission before any side effect (closing an authorization bypass), backed by new SQL-injection, write-permission, and secret-scan CI gates; the Accommodation Site is now the single source of a building's address (shown read-only, no more duplicate entry); building capacity derives from its rooms' beds; the Habitat Hub landing now carries onboarding; and an unused depreciation field was removed",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-06-13 17:30:00",
    },
    # [#c4d60j]
    {
        "title": "Apex 1.54.1 — reuse the existing Accommodation Manager role for cost-field privacy, sync the in-app changelog feed, harden the translation extractor so a Dynamic Link option (a fieldname) is no longer mis-translated and brand names stay in Latin, and correct the Salis worker-transport and fleet workspace routes (Masar, Fleet) and remove redundant workspace-to-workspace navigation links",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-13 09:00:00",
    },
    # [#a79v8y]
    {
        "title": "Apex 1.54.0 — finance-approved payment requests now post real payment documents (GL posting gated by a switch), a new policy-driven salary-deduction layer with Saudi labour-law caps and worker consent, cost figures hidden from non-finance roles, safety findings that auto-raise maintenance tickets, and a rider guard that blocks issuing a vehicle or fuel to a worker on leave",
        "app_name": "apex_habitat",
        "link": "/app/payment-request",
        "creation": "2026-06-12 09:00:00",
    },
    # [#1rsful]
    {
        "title": "Apex 1.53.3 — eight more core forms (Safety Inspection Report, Building License, Salis Vehicle, Salis Driver, Transport Request, Fuel Request, Rental Settlement) re-laid-out for clarity, completing the layout review of every core form; layout-only, no field or validation changed",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-06-11 12:00:00",
    },
    # [#j77kf6]
    {
        "title": "Apex 1.53.2 — five core forms (Accommodation Assignment, Checkout, Lease, Maintenance Request, Custody Issue) re-laid-out for clarity: fields grouped by purpose, audit fields tucked into collapsed System tabs, and long notes, tables and attachments given full-width rows; layout-focused, plus Accommodation Checkout's sensitive financial fields gated to a higher permission level",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-assignment",
        "creation": "2026-06-11 09:00:00",
    },
    # [#igkql7]
    {
        "title": "Apex 1.53.1 — Salis now cleanly separates vehicle custody (handover, fuel, maintenance for a person given a company car) from worker transport (moving workers by bus or taxi): transport requests are classified by trip type, and the two Salis workspaces are re-split into Worker Transport and Fleet & Vehicle Custody",
        "app_name": "apex_habitat",
        "link": "/app/transport-request",
        "creation": "2026-06-10 09:00:00",
    },
    # [#s9x5rt]
    {
        "title": "Apex 1.53.0 — a configurable Payment Router turns a finance-approved request into the payment document of your choice, app-wide finance options move into a new Apex Settings, all twelve workspaces are re-ordered to one canonical layout, forty-seven link fields auto-fill from their source, and twelve correctness bugs are fixed",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-06-09 09:00:00",
    },
    # [#o6upu5]
    {
        "title": "Apex 1.52.9 — a deep correctness pass: facility asset movements now actually move the asset, rental accruals get reconciled and stamped by their settlement, blocked submittable documents can be cancelled again, negative payment and claim amounts are rejected, and resident requests convert into the right maintenance, safety or custody document",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-06-08 12:00:00",
    },
    # [#fx8qbz]
    {
        "title": "Apex 1.52.8 — an app-wide form and workspace overhaul: every form is regrouped by concern, workspaces get wired-in charts, live quick-lists and shortcut tiles with live counts, building room and floor counts now compute correctly, and hundreds of Arabic section labels are added",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-06-08 09:00:00",
    },
    # [#7ncwsh]
    {
        "title": "Apex 1.52.7 — form-layout polish across 27 DocTypes: 25 single-purpose tabs removed, child tables moved full-width into their Overview tab and system fields collapsed, so no tab holds fewer than three fields; nothing was changed, only repositioned",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-06-07 12:00:00",
    },
    # [#bbpnya]
    {
        "title": "Apex 1.52.6 — reliability and hygiene: scheduler jobs read their settings once per batch, the cost-allocation ledger ignores duplicate-key races quietly, and a building's per-capacity cost zeroes when its capacity is removed",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-06-07 09:00:00",
    },
    # [#2r1tn6]
    {
        "title": "Apex 1.52.5 — the 11 app dashboards now provision the native Frappe way (is_standard module JSON, the same mechanism ERPNext uses) instead of Python seeders, auto-synced on install and migrate, with no dashboard, chart or number card lost",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-06-06 21:00:00",
    },
    # [#k2m474]
    {
        "title": "Apex 1.52.4 — security hardening: a custody-kiosk catalog leak is closed and worker passport/iqama PII plus the Masar token are now gated behind permission checks; native-first cleanups wire the Assigned-To panel into the idle-resident report; and the room generator now rejects two floor rows that resolve to the same floor code",
        "app_name": "apex_habitat",
        "link": "/app/custody-kiosk",
        "creation": "2026-06-06 18:00:00",
    },
    # [#8f8pnh]
    {
        "title": "Apex 1.52.3 — one consistent form layout across 13 Habitat and Salis DocTypes (named Overview / Related / System Info tabs, editable inputs left and computed values right), and two fixes: the Accommodation Assignment check-in photo now renders, and Accommodation Resident Request gets a proper field order",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-06-06 15:00:00",
    },
    # [#owzy47]
    {
        "title": "Apex 1.52.2 — a migrate-stability fix (Role Profiles no longer leave a stale lock on migrate), Accommodation Site now uses Frappe's native Address record with a one-time backfill, and a new Enable Email Notifications master switch in Habitat Settings (off by default) keeps the app from sending mail until the site is configured",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-site",
        "creation": "2026-06-06 12:00:00",
    },
    # [#53mv7d]
    {
        "title": "Apex 1.52.1 — stability and clarity across accommodation: a worker can no longer be placed in two beds at once, the housing picker lists only workers who still need a bed, and the building screen is tidier with capacity and occupancy shown together",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-06-06 09:30:00",
    },
    # [#d9qch1]
    {
        "title": "Apex 1.52.0 — Accommodation Building runs on its native sources: address reads from Frappe's Address record everywhere, the landlord is a Supplier auto-filled from the active lease, and annual rent is derived from the lease so figures can't drift; plus quick Activate / Deactivate for rooms and beds and an Edit Rooms & Beds button into the Room Setup wizard",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-06-06 09:00:00",
    },
    # [#m778yw]
    {
        "title": "Apex 1.51.1 — Arrivals Desk floor fixes (Ground floor rooms group under Ground Floor, basements label correctly, only truly floor-less rooms stay Unassigned) and the noisy Unknown readiness state is hidden; check-in now falls back to the company's default cost center, and an overdue maintenance ticket now raises a desk-visible Operations Alert",
        "app_name": "apex_habitat",
        "link": "/app/arrivals-desk",
        "creation": "2026-06-05 21:00:00",
    },
    # [#t8ymyu]
    {
        "title": "Apex 1.51.0 — a new staged Room Setup wizard (floors, room types, beds, approve) with functional floor numbering, My Work rebuilt on native widgets, and the Accommodation Building form gains a native Address widget, a Google Maps link, grouped Connections and a floor-layout dashboard, alongside a batch of production fixes",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-06-05 12:00:00",
    },
    # [#d3itby]
    {
        "title": "Apex 1.50.10 — My Work is now a universal work center: pending approvals from any workflow, assigned tasks, notifications, and mentions all in one place inside the workspace",
        "app_name": "apex_habitat",
        "link": "/app/my-work",
        "creation": "2026-06-05 09:00:00",
    },
    # [#tfp3q8]
    {
        "title": "Apex 1.50.8 — workspace names are now shorter and clearer: the main hub is Habitat Hub, daily housing work is under Housing, cleaning and fire safety under Safety, and app setup under Launchpad",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-06-04 12:00:00",
    },
    # [#dnhfjv]
    {
        "title": "Apex 1.35.0 — a Unified Action Inbox: one screen of only the documents awaiting your action (workflow approvals + your tasks), with inline Approve/Reject and a nightly cleanup of stale rows",
        "app_name": "apex_habitat",
        "link": "/app/action-inbox",
        "creation": "2026-05-28 09:00:00",
    },
    # [#a1n8mj]
    {
        "title": "Apex 1.34.0 — the Arrivals Desk is reworked from desk feedback: native Frappe styling, a full-width three-column layout, a multi-item custody store, one group QR (no pop-up), and signed check-in / custody / arrival-card prints with an embedded QR",
        "app_name": "apex_habitat",
        "link": "/app/arrivals-desk",
        "creation": "2026-05-27 09:00:00",
    },
    # [#ggkc46]
    {
        "title": "Apex 1.33.0 — the Arrivals Desk is rebuilt as one building-first screen: live floor-map, worker search, passport register, one-click housing (with over-capacity), custody, arrival card and multi-passenger transport",
        "app_name": "apex_habitat",
        "link": "/app/arrivals-desk",
        "creation": "2026-05-26 09:00:00",
    },
    # [#76gf6l]
    {
        "title": "Apex 1.32.0 — a Temporary Worker auto-links to his Employee when HR registers the matching passport (housing/custody re-pointed, cost back-dated)",
        "app_name": "apex_habitat",
        "link": "/app/temporary-worker",
        "creation": "2026-05-25 09:00:00",
    },
    # [#iwgq0i]
    {
        "title": "Apex 1.31.0 — custody records (issue, return, damage) can now name a Temporary Worker too, like the housing records",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-24 09:00:00",
    },
    # [#ia1wov]
    {
        "title": "Apex 1.30.0 — housing & worker records can now hold a passport-only Temporary Worker (pre-Iqama), with the Employee field kept in sync",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-23 09:00:00",
    },
    # [#eklfyr]
    {
        "title": "v1.29.1: Native-first cleanups \u2014 the room-label print format now ships as a standard format (installs on new sites); the monthly rent-due reminder is now a native Frappe Notification on the unpaid schedule (replacing a custom scheduler); and the duplicated worker-link dialog (QR + WhatsApp) was consolidated from three desk scripts into one shared bundle.",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-22 12:00:00",
    },
    # [#op68qe]
    {
        "title": "v1.29.0: Foundations for handling workers who arrive before they are registered \u2014 a new Temporary Worker record (keyed by passport, valid 30 days, extendable to 90) that will hold a new arrival's housing and custody until their Iqama is issued, then link to their permanent Employee. First step of the arrival redesign.",
        "app_name": "apex_habitat",
        "link": "/app/temporary-worker",
        "creation": "2026-05-22 09:00:00",
    },
    # [#sx4el9]
    {
        "title": "v1.28.3: Security \u2014 closed a project-boundary leak: a project-scoped fleet supervisor could open or API-fetch a Salis Driver or Passenger Manifest record from another project directly by name (the list view already hid them). Direct document access is now project-scoped too, and a driver can still read their own profile.",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-21 09:00:00",
    },
    # [#3wuxcb]
    {
        "title": "v1.28.2: The 16 operational notifications now ship as native standard JSON (auto-installed by Frappe on migrate) instead of being created by Python seed code — the same notifications, the same disabled-by-default behaviour, but the framework-native deployment path. Removed two seed modules and five seed patches.",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-20 09:00:00",
    },
    # [#61x285]
    {
        "title": "v1.28.1: The support-ticket SLA now uses the default Company's holiday list (the real business calendar) instead of whatever holiday list happened to exist, so SLA timers pause on the correct holidays.",
        "app_name": "apex_habitat",
        "link": "/app/issue",
        "creation": "2026-05-19 12:00:00",
    },
    # [#nv31rf]
    {
        "title": "Apex 1.28.0 — driver support tickets run on the native Issue desk with SLA",
        "app_name": "apex_habitat",
        "link": "/app/issue",
        "creation": "2026-05-19 09:00:00",
    },
    {
        "title": "v1.28.0: The custom Support Ticket was replaced by ERPNext's native Issue. A driver still raises and tracks tickets exactly as before in the portal, but they are now standard Issues with response/resolution SLA targets, a native communication timeline, and proper desk permissions (a driver sees only their own; fleet staff manage them). Don't-reinvent-the-wheel.",
        "app_name": "apex_habitat",
        "link": "/app/issue",
        "creation": "2026-05-19 09:01:00",
    },
    # [#nrzl1u]
    {
        "title": "v1.27.1: Restored the Safety onboarding (lost when Maintenance and Safety merged into Facilities), and surfaced two things that were built but not linked anywhere — the Cost by Dimension report (now in the Costs workspace) and the Arrivals Desk (now a shortcut in the Accommodation workspace).",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-18 12:00:00",
    },
    # [#e4ujzh]
    {
        "title": "Apex 1.27.0 — a one-screen Arrivals Desk for onboarding a worker",
        "app_name": "apex_habitat",
        "link": "/app/arrivals-desk",
        "creation": "2026-05-18 09:00:00",
    },
    {
        "title": "v1.27.0: New Arrivals Desk (/app/arrivals-desk) — pick an arriving worker and, from one screen, house them, issue their custody items, generate their personal Masar link + QR (and share it on WhatsApp), and request their transport. Each step reuses the existing flows; actions you lack permission for are disabled.",
        "app_name": "apex_habitat",
        "link": "/app/arrivals-desk",
        "creation": "2026-05-18 09:01:00",
    },
    # [#rm9zj3]
    {
        "title": "v1.26.4: Tidier desk navigation — Maintenance and Safety are merged into one 'Facilities' workspace, and Workers (transport) and Fuel are merged into one 'Movement' workspace. Fleet stays separate. Fewer, clearer areas to move between.",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-17 09:00:00",
    },
    {
        "title": "v1.26.4: Reliability — the workflow, navbar and dashboard seeds now log before rolling back and roll back only their own item (a per-item savepoint), so one bad record can no longer silently discard the others seeded in the same run.",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-17 09:01:00",
    },
    # [#an1fd6]
    {
        "title": "v1.26.3: Transport now clearly separates worker (bus/shuttle) trips from representative trips — a representative trip names the representative and can never carry labour-accommodation or a worker manifest, and only worker trips appear in the worker (Masar) view. Plus seed-reliability fixes and a clearer Employee 'Salis' connections label.",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-16 09:00:00",
    },
    # [#903kea]
    {
        "title": "v1.26.2: Retired the old custom approval authority-tier engine and its now-unused 'Approval Request' record. Approvals run entirely on native Frappe Workflow (since 1.26.0), so the parallel mechanism, its settings ladder and its dashboard card were removed. Segregation-of-duties (no self-approval) is unchanged.",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-15 09:00:00",
    },
    # [#aak6og]
    {
        "title": "v1.26.1: Removed the out-of-scope 'Sponsorship Transfer Case' document (a kafala-transfer / Qiwa tracking record). It is a government-relations process that does not serve the accommodation-cost and fleet-operations core, so it and its workflow, report card and permissions were removed cleanly.",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-14 12:00:00",
    },
    # [#8ya2c9]
    {
        "title": "Apex 1.26.0 — Salis approvals run on native Frappe Workflow",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-14 09:00:00",
    },
    {
        "title": "v1.26.0: Approval authority for the six Salis approval documents (Fuel Request, Fuel Claim, Fuel Exception Case, Movement Cost Recovery, Movement Cost Transfer, Vehicle Damage Write-Off) now lives entirely in native Frappe Workflows — one approval mechanism instead of two — with the same authorized approvers and maker-cannot-approve-their-own rule.",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-14 09:01:00",
    },
    {
        "title": "v1.26.0: The movement-cost recovery / transfer and vehicle damage write-off documents gained their own native approval workflows, replacing the custom authority-tier engine.",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-14 09:02:00",
    },
    # [#tm15st]
    {
        "title": "Apex 1.25.0 — a formal safety-incident record with management escalation, and hardened worker links",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-13 09:00:00",
    },
    {
        "title": "v1.25.0: New Habitat Safety Incident record — log an accommodation safety incident with a severity, casualties and the immediate action taken; a severe or critical incident automatically notifies management. Severity must be chosen explicitly so nothing is silently filed as low.",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-13 09:01:00",
    },
    {
        "title": "v1.25.0: The Masar worker links are hardened — the guest endpoints are rate-limited against abuse, and a link stops working once the worker is marked Left or Inactive even if it was never revoked.",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-13 09:02:00",
    },
    # [#o20n9n]
    {
        "title": "Apex 1.24.0 — issuing a worker's Masar link is now easy, with a working QR and a WhatsApp share",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-12 09:00:00",
    },
    {
        "title": "v1.24.0: A supervisor can issue a worker's personal Masar link straight from the Accommodation Assignment form ('Issue Masar Link'), see a scannable QR code (now rendered reliably), and share the link to the worker's number over WhatsApp from the browser — no integration needed",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-12 09:01:00",
    },
    {
        "title": "v1.24.0: Issuing a worker link is now allowed for accommodation supervisors, HR and fleet supervisors; the Masar Worker Token record moved into Apex Core as shared access infrastructure",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-12 09:02:00",
    },
    # [#g9myv1]
    {
        "title": "Apex 1.23.0 — Masar becomes a complete worker self-service app",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-10 09:00:00",
    },
    {
        "title": "v1.23.0: Masar (/masar) is now a mobile worker app — a housed-and-transported employee opens a personal link and sees their profile and documents, their accommodation (building, room, in-charge contact), and their transport (pickup, route, vehicle, driver), and can raise requests. The old driver 'my route today' view moved into the driver portal where it belongs",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-10 09:01:00",
    },
    {
        "title": "v1.23.0: A new 'Cost by Dimension' report breaks accommodation cost down by company, building and project; the Fuel Approval Console no longer shows stray markup on its metric tiles; and City now links to a real Country",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-10 09:02:00",
    },
    # [#4p9wka]
    {
        "title": "Apex 1.22.1 — the desk pages are more robust, dynamic, and comfortable",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-09 09:00:00",
    },
    {
        "title": "v1.22.1: The six operational desk pages (Front Desk, Custody Kiosk, Safety Map, Transfer Board, Fuel Approval Console, Dispatch Board) now show loading / empty / error-with-retry states instead of failing silently, and ~24 real bugs (silent failures, a stale-response race, double-submit gaps) were fixed",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-09 09:01:00",
    },
    {
        "title": "v1.22.1: Loading skeletons, debounced search, double-submit guards, and accessibility touches make the desk pages feel livelier",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-09 09:02:00",
    },
    # [#hoxbco]
    {
        "title": "Apex 1.22.0 — a new Gemini portal theme, a genuinely Frappe-styled theme, and a fixed worker-route page",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-08 09:00:00",
    },
    {
        "title": "v1.22.0: The driver portal gains a premium dark 'Gemini' theme, and the 'Frappe Standard' theme was redesigned to genuinely look like Frappe (distinct layout, not just colours) — choose either in Salis Portal Theme settings",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-08 09:01:00",
    },
    {
        "title": "v1.22.0: The worker-route page (/masar) no longer errors on load, the Apex Core workspace is restored to a complete organised hub, and newly-added desk strings are now in Arabic",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-08 09:02:00",
    },
    # [#oj1uv4]
    {
        "title": "Apex 1.21.0 — a clean settings hub, KPI tiles on every Salis workspace, and a training guide",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-07 09:00:00",
    },
    {
        "title": "v1.21.0: The Apex Core workspace is now a focused settings hub (the four settings + the driver-portal theme up front, master-data clutter removed), and every Salis workspace shows at-a-glance KPI number cards",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-07 09:01:00",
    },
    {
        "title": "v1.21.0: Added a per-DocType training guide, removed deprecated dead code (Habitat Operations Alert, the empty habitat_city), and added a 'my worker route today' page for workers",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-07 09:02:00",
    },
    # [#l9xw8i]
    {
        "title": "Apex 1.20.0 — driver portal: language toggle, profile and vehicle views",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-06 09:00:00",
    },
    {
        "title": "v1.20.0: Each driver can switch the portal between English and Arabic (full right-to-left layout); English stays the default and the choice is remembered on the device",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-06 09:01:00",
    },
    {
        "title": "v1.20.0: New driver profile and vehicle pages - a driver can view their own profile (license, status, project) and their assigned vehicle's details",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-06 09:02:00",
    },
    # [#td6t06]
    {
        "title": "Apex 1.19.1 — Arabic module names, a tidier settings hub, and a cleaner portal",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-05 09:00:00",
    },
    {
        "title": "v1.19.1: Modules now read with proper Arabic names on the desk (Apex, Salis and Habitat), and the Apex Core settings hub is reorganised with the driver-portal theme surfaced",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-05 09:01:00",
    },
    {
        "title": "v1.19.1: The driver portal's actions no longer force an early commit, so it no longer leaves stray records on a dev/test site and test runs stay isolated",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-05 09:02:00",
    },
    # [#etjj4s]
    {
        "title": "Apex 1.19.0 — a themeable driver portal and a fully Arabic desk",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-04 09:00:00",
    },
    {
        "title": "v1.19.0: The driver portal has a new mobile-first design with three selectable themes (AFMCO, Frappe Standard, Dark) chosen from Salis Portal Theme settings; it stays in English for a multilingual driver workforce",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-04 09:01:00",
    },
    {
        "title": "v1.19.0: Over 300 desk strings (onboarding, reports, charts, number cards, dashboards, workspaces, Integration Settings) are now translated to Arabic, and the Habitat workspace label is corrected",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-04 09:02:00",
    },
    # [#n05arv]
    {
        "title": "Apex 1.18.4 — driver portal check-ins now record attendance",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-03 09:00:00",
    },
    {
        "title": "v1.18.4: A portal check-in now submits the attendance record, so the missing-attendance watcher recognises it and any open missing-attendance alert auto-resolves",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-03 09:01:00",
    },
    {
        "title": "v1.18.4: Updating an existing site can no longer fail on the fuel-ledger unique index - a new patch removes any duplicate rows before the constraint is applied",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-03 09:02:00",
    },
    # [#pwibzt]
    {
        "title": "Apex 1.18.3 — leaner Arabic translations",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-02 09:00:00",
    },
    {
        "title": "v1.18.3: Standard Frappe terms (statuses, months, generic labels) now use Frappe's own Arabic translations; the app's file keeps only its domain-specific Salis and Habitat strings",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-02 09:01:00",
    },
    {
        "title": "v1.18.3: Terms Frappe does not translate (such as Approved) are retained, so no label regresses to English",
        "app_name": "apex_habitat",
        "link": "/app",
        "creation": "2026-05-02 09:02:00",
    },
    # [#66do42]
    {
        "title": "Apex 1.18.2 — vehicle, driver and passenger-manifest lists are now project-scoped",
        "app_name": "apex_habitat",
        "link": "/app/salis-vehicle",
        "creation": "2026-05-01 09:00:00",
    },
    {
        "title": "v1.18.2: A supervisor scoped to a project now sees only that project's vehicles, drivers and passenger manifests in the desk lists - closing a list-enumeration gap",
        "app_name": "apex_habitat",
        "link": "/app/salis-vehicle",
        "creation": "2026-05-01 09:01:00",
    },
    {
        "title": "v1.18.2: A driver still sees their own driver profile - the self-profile view is preserved",
        "app_name": "apex_habitat",
        "link": "/app/salis-driver",
        "creation": "2026-05-01 09:02:00",
    },
    # [#cvumqa]
    {
        "title": "Apex 1.18.1 — a rental payment request can only be raised on an approved settlement",
        "app_name": "apex_habitat",
        "link": "/app/rental-settlement",
        "creation": "2026-04-30 09:00:00",
    },
    {
        "title": "v1.18.1: A payment request can no longer be raised on a disputed or not-yet-approved rental settlement - only on an Approved one",
        "app_name": "apex_habitat",
        "link": "/app/rental-settlement",
        "creation": "2026-04-30 09:01:00",
    },
    {
        "title": "v1.18.1: This protects the finance flow - a contested settlement cannot be paid until it is resolved and approved",
        "app_name": "apex_habitat",
        "link": "/app/rental-settlement",
        "creation": "2026-04-30 09:02:00",
    },
    # [#154zvc]
    {
        "title": "Apex 1.18.0 — worker-movement foundations: housing-linked pickups and trip boarding logs",
        "app_name": "apex_habitat",
        "link": "/app/trip-start-log",
        "creation": "2026-04-29 09:00:00",
    },
    {
        "title": "v1.18.0: A route stop can now be linked to a worker's housing building, and a new Trip Start Log records who boarded where - by QR or manual check-in, including unregistered contractors",
        "app_name": "apex_habitat",
        "link": "/app/trip-start-log",
        "creation": "2026-04-29 09:01:00",
    },
    {
        "title": "v1.18.0: A driver can fetch today's worker route, stops, housing pickups and manifest from one identity-scoped endpoint - the foundation for the worker-movement experience",
        "app_name": "apex_habitat",
        "link": "/app/trip-start-log",
        "creation": "2026-04-29 09:02:00",
    },
    # [#ciaygl]
    {
        "title": "Apex 1.17.0 — an integration kit so any frontend can use Apex as its backend",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-04-28 09:00:00",
    },
    {
        "title": "v1.17.0: Apex now ships a public integration guide and an Apex Integration Settings page — install it as a backend and drive it over a clean, token-authenticated API",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-04-28 09:01:00",
    },
    {
        "title": "v1.17.0: The Apex Core workspace is reorganized into clear sections (Settings, Integration, Habitat Setup, Salis Setup, Console), and What's-New links now point to the right place",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-04-28 09:02:00",
    },
    # [#99u94j]
    {
        "title": "Apex 1.16.0 — settings, console and Salis setup unified in one Apex Core workspace",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-04-27 09:00:00",
    },
    {
        "title": "v1.16.0: The Habitat Setup, Habitat Console and Salis Setup workspaces are merged into a single Apex Core workspace, so all configuration and admin tools share one home",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-04-27 09:01:00",
    },
    {
        "title": "v1.16.0: Less sidebar clutter — three separate admin workspaces become one, with every link, shortcut and card carried over",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-04-27 09:02:00",
    },
    # [#hc0v4w]
    {
        "title": "Apex 1.15.0 — shared settings get a dedicated Apex Core workspace",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-04-26 09:00:00",
    },
    {
        "title": "v1.15.0: Habitat Settings and Salis Settings now live in a dedicated Apex Core workspace, so configuration has a clear home in the desk",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-04-26 09:01:00",
    },
    {
        "title": "v1.15.0: The Apex Core workspace is available to System Manager and the Accommodation and Fleet managers who own those settings",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-04-26 09:02:00",
    },
    # [#d9wdv4]
    {
        "title": "Apex 1.14.2 — a refreshed, mobile-first driver portal and a cleaner fuel approval board",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-04-25 09:00:00",
    },
    {
        "title": "v1.14.2: The driver portal is redesigned for phones — a branded home with your status, vehicle and license at a glance, icon navigation, and large touch-friendly actions",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-04-25 09:01:00",
    },
    {
        "title": "v1.14.2: The Fuel Approval Console is easier to scan — each request leads with the driver and vehicle, flags over-threshold requests first, and lays out as clean cards",
        "app_name": "apex_habitat",
        "link": "/app/fuel-approval-console",
        "creation": "2026-04-25 09:02:00",
    },
    # [#3hjmqb]
    {
        "title": "Apex 1.14.1 — the driver portal opens reliably for signed-in users",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-04-24 09:00:00",
    },
    {
        "title": "v1.14.1: Signed-in drivers and staff can now open the driver portal without it failing to load",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-04-24 09:01:00",
    },
    {
        "title": "v1.14.1: Security and reliability improvements, plus a refreshed project overview",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-04-24 09:02:00",
    },
    # [#jojwcl]
    {
        "title": "Apex 1.14.0 — operations alerts clear themselves more completely and keep a resolution trail",
        "app_name": "apex_habitat",
        "link": "/app/operations-alert",
        "creation": "2026-04-23 09:00:00",
    },
    {
        "title": "v1.14.0: When the cause behind an alert is fixed it now closes on its own — including excessive fuel top-up alerts, which clear when the top-up is reverted or the quota is back in range",
        "app_name": "apex_habitat",
        "link": "/app/operations-alert",
        "creation": "2026-04-23 09:01:00",
    },
    {
        "title": "v1.14.0: Resolved alerts now record when they cleared and why, so your open-alerts view shows only what still needs attention",
        "app_name": "apex_habitat",
        "link": "/app/operations-alert",
        "creation": "2026-04-23 09:02:00",
    },
    # [#c4oi4d]
    {
        "title": "Apex 1.13.0 — dispatch trips now run on a workflow, completing the Movement approval suite",
        "app_name": "apex_habitat",
        "link": "/app/dispatch-trip",
        "creation": "2026-04-22 09:00:00",
    },
    {
        "title": "v1.13.0: A dispatch trip moves Planned → Dispatched → Completed, and completing it automatically marks the linked transport request fulfilled and advances the vehicle odometer",
        "app_name": "apex_habitat",
        "link": "/app/dispatch-trip",
        "creation": "2026-04-22 09:01:00",
    },
    {
        "title": "v1.13.0: Every Movement document — requests, settlements, clearances, payments, tickets, sponsorship transfers, fuel and now trips — runs on a guided, role-based workflow",
        "app_name": "apex_habitat",
        "link": "/app/dispatch-trip",
        "creation": "2026-04-22 09:02:00",
    },
    # [#m931mv]
    {
        "title": "Apex 1.12.0 — fuel claims and exception cases now run on guided approval workflows",
        "app_name": "apex_habitat",
        "link": "/app/fuel-claim",
        "creation": "2026-04-21 09:00:00",
    },
    {
        "title": "v1.12.0: A fuel claim now follows a clear path — submit to Movement, reconcile, approve, close — and the person who raised it cannot approve their own",
        "app_name": "apex_habitat",
        "link": "/app/fuel-claim",
        "creation": "2026-04-21 09:01:00",
    },
    {
        "title": "v1.12.0: Fuel exception cases move through an investigation flow — open, investigate, request evidence, resolve or reject, close — with evidence required before resolution",
        "app_name": "apex_habitat",
        "link": "/app/fuel-exception-case",
        "creation": "2026-04-21 09:02:00",
    },
    # [#jmldyn]
    {
        "title": "Apex 1.11.0 — fuel requests now run on a clear, role-based approval workflow",
        "app_name": "apex_habitat",
        "link": "/app/fuel-request",
        "creation": "2026-04-20 09:00:00",
    },
    {
        "title": "v1.11.0: Every fuel request moves through request → approve → complete with a clear status, and the person who raises a request can no longer approve their own",
        "app_name": "apex_habitat",
        "link": "/app/fuel-request",
        "creation": "2026-04-20 09:01:00",
    },
    {
        "title": "v1.11.0: The Fuel Approval Console now drives the same workflow — approve or send back a request, and quotas apply on approval and reverse on cancellation",
        "app_name": "apex_habitat",
        "link": "/app/fuel-request",
        "creation": "2026-04-20 09:02:00",
    },
    # [#f5ee56]
    {
        "title": "Apex 1.10.0 — fuel requests, top-ups and chip actions are now one screen",
        "app_name": "apex_habitat",
        "link": "/app/fuel-request",
        "creation": "2026-04-19 09:00:00",
    },
    {
        "title": "v1.10.0: Fuel requests, quota top-ups and fuel-chip actions are now a single Fuel Request — pick the type and only the fields you need appear",
        "app_name": "apex_habitat",
        "link": "/app/fuel-request",
        "creation": "2026-04-19 09:01:00",
    },
    {
        "title": "v1.10.0: Temporary fuel top-ups now reliably revert on their due date, so a vehicle's quota no longer quietly drifts upward",
        "app_name": "apex_habitat",
        "link": "/app/fuel-request",
        "creation": "2026-04-19 09:02:00",
    },
    # [#c5us3s]
    {
        "title": "Apex 1.9.1 — the Driver Portal opens reliably for everyone",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-04-18 09:00:00",
    },
    {
        "title": "v1.9.1: The Driver Portal now loads a driver's home screen reliably, and shows a clear message if it can't load instead of a misleading 'not linked'",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-04-18 09:01:00",
    },
    {
        "title": "v1.9.1: Signed in as a manager? The portal shows a helpful screen with quick links to your Salis areas instead of a dead-end",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-04-18 09:02:00",
    },
    # [#akdx2l]
    {
        "title": "Apex 1.9.0 — payments, support tickets and sponsorship transfers move on a real workflow",
        "app_name": "apex_habitat",
        "link": "/app/salis-payment-request",
        "creation": "2026-04-17 09:00:00",
    },
    {
        "title": "v1.9.0: Salis Payment Requests follow a finance approval flow — only Finance approves and marks paid, and no one approves their own request",
        "app_name": "apex_habitat",
        "link": "/app/salis-payment-request",
        "creation": "2026-04-17 09:01:00",
    },
    {
        "title": "v1.9.0: Support Tickets move through a clear status workflow, and sponsorship transfers complete only when Qiwa and clearance are done",
        "app_name": "apex_habitat",
        "link": "/app/support-ticket",
        "creation": "2026-04-17 09:02:00",
    },
    # [#dwvjvo]
    {
        "title": "Apex 1.8.0 — more Movement documents move on a real approval workflow",
        "app_name": "apex_habitat",
        "link": "/app/rental-settlement",
        "creation": "2026-04-16 09:00:00",
    },
    {
        "title": "v1.8.0: Rental Settlements now follow a clear approval flow with a Finance-only 'Mark Paid' step",
        "app_name": "apex_habitat",
        "link": "/app/rental-settlement",
        "creation": "2026-04-16 09:01:00",
    },
    {
        "title": "v1.8.0: Driver Clearance is a workflow that only clears a driver once fuel, custody and vehicle returns are settled — and post-approval steps now work",
        "app_name": "apex_habitat",
        "link": "/app/driver-clearance",
        "creation": "2026-04-16 09:02:00",
    },
    # [#1pwyu4]
    {
        "title": "Apex 1.7.0 — Transport Requests run on a real approval workflow, with sharper reports and sturdier engines",
        "app_name": "apex_habitat",
        "link": "/app/transport-request",
        "creation": "2026-04-15 09:00:00",
    },
    {
        "title": "v1.7.0: Transport Requests now move through a proper approval workflow — action buttons, the right approver at each step, and the post-approval steps actually work",
        "app_name": "apex_habitat",
        "link": "/app/transport-request",
        "creation": "2026-04-15 09:01:00",
    },
    {
        "title": "v1.7.0: Cost and fleet reports gain Project / Company / Cost Center filters and inline charts",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-15 09:02:00",
    },
    {
        "title": "v1.7.0: More dependable fuel accrual, self-clearing operational alerts, and reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-15 09:03:00",
    },
    # [#ecvzua]
    {
        "title": "Apex 1.6.1 — a focused desk that opens to your Apex areas",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-14 09:00:00",
    },
    # [#69cqpa]
    {
        "title": "Apex 1.6.0 — shared settings now live together in one Apex Core area",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-04-13 09:00:00",
    },
    # [#67f7b9]
    {
        "title": "Apex 1.5.0 — connected records everywhere, a Salis getting-started guide, and cleaner navigation",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-12 09:00:00",
    },
    {
        "title": "v1.5.0: Open a record and see everything related to it in the Connections tab — across vehicles, drivers, custody, maintenance, leases and more",
        "app_name": "apex_habitat",
        "link": "/app/salis-vehicle",
        "creation": "2026-04-12 09:01:00",
    },
    {
        "title": "v1.5.0: A new Salis 'Go-Live' guide walks you through your first vehicle, driver, assignment and trip",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-12 09:02:00",
    },
    {
        "title": "v1.5.0: Reach your Salis dashboards and trend charts straight from the workspace, with shorter, clearer area names",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-12 09:03:00",
    },
    {
        "title": "v1.5.0: Optional email templates and scheduled email reports for the Movement team, plus reliability and tidiness improvements",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-12 09:04:00",
    },
    # [#ri9jlm]
    {
        "title": "Apex 1.4.1 — security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-11 09:00:00",
    },
    # [#gdq4av]
    {
        "title": "Apex 1.4.0 — Movement costs now carry Company and Cost Center, with quicker navigation",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-10 09:00:00",
    },
    {
        "title": "v1.4.0: Rentals, fuel claims, payments and cost recoveries now record their Company and Cost Center — so finance can filter and group Movement costs cleanly",
        "app_name": "apex_habitat",
        "link": "/app/rental-settlement",
        "creation": "2026-04-10 09:01:00",
    },
    {
        "title": "v1.4.0: Salis areas have short, clear names and a Help-menu shortcut, so you reach the Dispatch Board and your work area in one click",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-10 09:02:00",
    },
    # [#rxmz10]
    {
        "title": "Apex 1.3.0 — quicker Salis navigation, one-tap record creation and a leaner role setup",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-09 09:00:00",
    },
    {
        "title": "v1.3.0: Jump straight to the area you work in — Workers Transport, Representatives Fleet, Fuel, Rentals, Compliance and Setup",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-09 09:01:00",
    },
    {
        "title": "v1.3.0: Create as you go — new driver, vehicle, trip or fuel request right from each Salis area",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-09 09:02:00",
    },
    {
        "title": "v1.3.0: A simpler set of roles that fits a focused team, plus security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-09 09:03:00",
    },
    # [#6dgmgf]
    {
        "title": "Apex 1.2.0 — Salis gets a live dispatch board, deeper dashboards, printable documents and smarter alerts",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-08 09:00:00",
    },
    {
        "title": "v1.2.0: A new Dispatch Board shows your fleet, today's trips and which drivers are free — all on one screen",
        "app_name": "apex_habitat",
        "link": "/app/salis-dispatch-board",
        "creation": "2026-04-08 09:01:00",
    },
    {
        "title": "v1.2.0: Print clean handover receipts, fuel vouchers, rental settlement statements and driver clearance certificates",
        "app_name": "apex_habitat",
        "link": "/app/vehicle-handover",
        "creation": "2026-04-08 09:02:00",
    },
    {
        "title": "v1.2.0: New reports at your fingertips — vehicle utilisation, fuel spend by vehicle, rental cost by office, fulfilment SLA and recovery aging",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-08 09:03:00",
    },
    {
        "title": "v1.2.0: Salis now reaches out — alerts for expiring compliance, blocked clearances and overdue fuel, and it routes new work to the right person",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-08 09:04:00",
    },
    {
        "title": "v1.2.0: Find your way by area — Workers Transport, Representatives Fleet, Fuel, Rentals, Compliance and Setup each get their own space",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-08 09:05:00",
    },
    # [#bqym77]
    {
        "title": "Apex 1.1.1 — security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-07 09:00:00",
    },
    # [#bgr3hf]
    {
        "title": "Apex 1.1.0 — Salis opens to the numbers that matter, on a cleaner two-division workspace",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-06 09:00:00",
    },
    {
        "title": "v1.1.0: See your fleet at a glance — active vehicles, vehicles in the shop, open transport requests and pending approvals greet you the moment Salis opens",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-06 09:01:00",
    },
    {
        "title": "v1.1.0: Read status at a glance — colour-coded vehicles, drivers, trips, fuel, maintenance and accommodation, everywhere you look (list, Kanban, Calendar and Report)",
        "app_name": "apex_habitat",
        "link": "/app/salis-vehicle",
        "creation": "2026-04-06 09:02:00",
    },
    # [#86cegm]
    {
        "title": "Apex 1.0.1 — security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-04-05 09:00:00",
    },
    # [#klme55]
    {
        "title": "Apex 1.0.0 — your workforce operations, end to end: where they live and how they move, now in one suite",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-04-04 09:00:00",
    },
    # [#s1qsym]
    {
        "title": "v1.0.0: Meet Salis — take command of every vehicle, driver, trip and litre of fuel from one Movement workspace",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-03 09:00:00",
    },
    {
        "title": "v1.0.0: Run both sides of Movement from one place — shuttle workers from camp to site and across cities, and keep your representatives' cars, trips and fuel on track",
        "app_name": "apex_habitat",
        "link": "/app/transport-request",
        "creation": "2026-04-03 09:01:00",
    },
    {
        "title": "v1.0.0: Every fuel, transport and transfer request finds the right approver automatically — small ones clear fast, big ones escalate up the chain on their own",
        "app_name": "apex_habitat",
        "link": "/app/approval-request",
        "creation": "2026-04-03 09:02:00",
    },
    {
        "title": "v1.0.0: Clear pending fuel requests in seconds from the Fuel Approval Console, and settle any disputed fuel cleanly with an evidence-backed exception case",
        "app_name": "apex_habitat",
        "link": "/app/fuel-approval-console",
        "creation": "2026-04-03 09:03:00",
    },
    {
        "title": "v1.0.0: Watch rental costs add up day by day, close the month with one Rental Settlement, and hand finance a ready-to-pay request",
        "app_name": "apex_habitat",
        "link": "/app/rental-settlement",
        "creation": "2026-04-03 09:04:00",
    },
    {
        "title": "v1.0.0: Put the Driver Portal in every driver's pocket — check in, see today's trips, request fuel and raise a ticket from a phone at /driver",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-04-03 09:05:00",
    },
    {
        "title": "v1.0.0: Open any Employee or Supplier and see their Movement story right there — driver record, trips and rental activity, one click away",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-04-03 09:06:00",
    },
    # [#kq2jpk]
    {
        "title": "Apex Habitat v0.9.1 — guided setup is back, and every record shows what it's connected to",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-04-01 09:30:00",
    },
    {
        "title": "v0.9.1: Never wonder where to start — step-by-step setup banners now guide you through Setup, Accommodation and Safety",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-04-01 09:31:00",
    },
    {
        "title": "v0.9.1: Open a building and see its whole world in one tab — rooms, beds, residents, leases, custody and more, all one click away",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-04-01 09:32:00",
    },
    # [#kwjxwv]
    {
        "title": "v0.9.0: Stop typing, start tapping — move residents, inspect rooms and issue gear from fast, visual boards",
        "app_name": "apex_habitat",
        "link": "/app/transfer-board",
        "creation": "2026-03-30 09:00:00",
    },
    {
        "title": "v0.9.0: Move a resident between buildings with a single drag — pull one bed onto another and you're done",
        "app_name": "apex_habitat",
        "link": "/app/transfer-board",
        "creation": "2026-03-30 09:01:00",
    },
    {
        "title": "v0.9.0: Walk your buildings on a live Safety Map — rooms needing attention pulse for you; tap one to log an inspection on the spot",
        "app_name": "apex_habitat",
        "link": "/app/safety-map",
        "creation": "2026-03-30 09:02:00",
    },
    {
        "title": "v0.9.0: Hand out custody like a checkout counter — tap big item tiles into a cart and issue, all from the Custody Kiosk",
        "app_name": "apex_habitat",
        "link": "/app/custody-kiosk",
        "creation": "2026-03-30 09:03:00",
    },
    {
        "title": "v0.9.0: Check in the right person every time — Front Desk now shows the worker's photo and saves a room-condition snapshot at handover",
        "app_name": "apex_habitat",
        "link": "/app/front-desk",
        "creation": "2026-03-30 09:04:00",
    },
    # [#gcm1z2]
    {
        "title": "Apex Habitat v0.8.6 — check residents in and out from a visual board, and never lose track of an idle worker",
        "app_name": "apex_habitat",
        "link": "/app/front-desk",
        "creation": "2026-03-21 09:00:00",
    },
    {
        "title": "v0.8.6: Run the front desk by colour — tap a green bed to check someone in, a red bed to check them out",
        "app_name": "apex_habitat",
        "link": "/app/front-desk",
        "creation": "2026-03-21 09:01:00",
    },
    {
        "title": "v0.8.6: Resident Supervisors can now check residents in and out themselves, right from the Front Desk board",
        "app_name": "apex_habitat",
        "link": "/app/front-desk",
        "creation": "2026-03-21 09:02:00",
    },
    {
        "title": "v0.8.6: Stop paying for forgotten workers — flag an idle resident and Apex routes a follow-up to the right team and counts the days and the cost for you",
        "app_name": "apex_habitat",
        "link": "/app/idle-resident-report",
        "creation": "2026-03-21 09:03:00",
    },
    # [#kcevly]
    {
        "title": "Apex Habitat v0.8.5 — book short stays with a clear end date, and start holding idle workers to account",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-assignment",
        "creation": "2026-03-20 21:00:00",
    },
    {
        "title": "v0.8.5: Book a stay as permanent or temporary and set an expected check-out date, so short stays never quietly become permanent",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-assignment",
        "creation": "2026-03-20 21:01:00",
    },
    {
        "title": "v0.8.5: Catch a stay before it overruns — a daily watchlist flags temporary residents nearing or past their check-out date",
        "app_name": "apex_habitat",
        "link": "/app/habitat-settings",
        "creation": "2026-03-20 21:02:00",
    },
    {
        "title": "v0.8.5: Spotlight workers living in camp but not yet deployed, and put a name to who owns getting them moving",
        "app_name": "apex_habitat",
        "link": "/app/idle-resident-report",
        "creation": "2026-03-20 21:03:00",
    },
    # [#p7qhza]
    {
        "title": "Apex Habitat v0.8.4 — let the right reports, reminders and follow-ups send themselves",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-03-20 18:00:00",
    },
    {
        "title": "v0.8.4: Have your key reports land in inboxes on schedule — supplier cost recovery, occupancy trend, maintenance backlog and task compliance, sent automatically once you turn them on",
        "app_name": "apex_habitat",
        "link": "/app/auto-email-report",
        "creation": "2026-03-20 18:01:00",
    },
    {
        "title": "v0.8.4: Send polished renewal and acknowledgement emails in a click, with ready-made templates for licences, leases and resident requests",
        "app_name": "apex_habitat",
        "link": "/app/email-template",
        "creation": "2026-03-20 18:02:00",
    },
    {
        "title": "v0.8.4: Nothing slips through the cracks — assigning a resident request drops a follow-up into that person's to-do list, and closing the request ticks it off",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-resident-request",
        "creation": "2026-03-20 18:03:00",
    },
    {
        "title": "v0.8.4: Jump straight to the Command Center or Setup from the Help menu — your key workspaces are always one click away",
        "app_name": "apex_habitat",
        "link": "/app/operations-command-center",
        "creation": "2026-03-20 18:04:00",
    },
    # [#ad5wxy]
    {
        "title": "Apex Habitat v0.8.3 — see your work on a calendar, move it across a board, and let it route itself",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-03-20 15:00:00",
    },
    {
        "title": "v0.8.3: See what's due on a calendar — scheduled tasks, licence and lease dates, and service orders, laid out by date",
        "app_name": "apex_habitat",
        "link": "/app/scheduled-task-instance/view/calendar",
        "creation": "2026-03-20 15:01:00",
    },
    {
        "title": "v0.8.3: Turn rooms around faster — drag each room from Needs Cleaning to Ready on a housekeeping board",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-room/view/kanban",
        "creation": "2026-03-20 15:02:00",
    },
    {
        "title": "v0.8.3: Let new maintenance and resident requests assign themselves to your team — just add your people and switch it on",
        "app_name": "apex_habitat",
        "link": "/app/assignment-rule",
        "creation": "2026-03-20 15:03:00",
    },
    {
        "title": "v0.8.3: Keep your team in the loop automatically — opt-in alerts when a request is assigned, raised, waiting on evidence, or carries a damage assessment",
        "app_name": "apex_habitat",
        "link": "/app/notification",
        "creation": "2026-03-20 15:04:00",
    },
    # [#4x2rz9]
    {
        "title": "Apex Habitat v0.8.2 — every building becomes its own store, with stock you can track and move",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-stock-ledger",
        "creation": "2026-03-20 12:00:00",
    },
    {
        "title": "v0.8.2: Always know what's in each building — issue and return custody and watch stock move in and out, item by item",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-stock-ledger",
        "creation": "2026-03-20 12:01:00",
    },
    {
        "title": "v0.8.2: Send supplies between buildings with confidence — ship a transfer, mark it received on arrival, and never move more than a store actually holds",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-material-transfer",
        "creation": "2026-03-20 12:02:00",
    },
    {
        "title": "v0.8.2: Keep finance in the picture — moving stock across cost centres sends them a heads-up memo, automatically",
        "app_name": "apex_habitat",
        "link": "/app/habitat-settings",
        "creation": "2026-03-20 12:03:00",
    },
    {
        "title": "v0.8.2: Know exactly what you have and what it's worth — on-hand quantity and value for every store and every employee's custody, in one report",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-stock-balance/view/report",
        "creation": "2026-03-20 12:04:00",
    },
    {
        "title": "v0.8.2: Triage at a glance — drag resident and maintenance requests across status columns on their own boards",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-resident-request/view/kanban",
        "creation": "2026-03-20 12:05:00",
    },
    # [#lxtpx4]
    {
        "title": "Apex Habitat v0.8.0 — bill suppliers back, see occupancy trends, and print every handover",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-03-20 09:00:00",
    },
    {
        "title": "v0.8.0: Recover what suppliers' workers cost you — a monthly report totals each supplier's housing cost and adds your markup, ready to bill",
        "app_name": "apex_habitat",
        "link": "/app/supplier-cost-recovery/view/report",
        "creation": "2026-03-20 09:01:00",
    },
    {
        "title": "v0.8.0: Get expiry and overdue alerts right where you work — posted on the document's own timeline and, if you like, straight to your inbox",
        "app_name": "apex_habitat",
        "link": "/app/habitat-settings",
        "creation": "2026-03-20 09:02:00",
    },
    {
        "title": "v0.8.0: See how full your buildings have been over time — a new Occupancy Trend report charts the lows, averages, highs and days over capacity",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-occupancy-snapshot",
        "creation": "2026-03-20 09:03:00",
    },
    {
        "title": "v0.8.0: Print a signed handover in seconds — bilingual receipts for custody issue and return, checkout clearance, damage notices and work orders",
        "app_name": "apex_habitat",
        "link": "/app/custody-issue",
        "creation": "2026-03-20 09:04:00",
    },
    {
        "title": "v0.8.0: Keep an eye on the whole operation from one System Administration workspace, with fresh cards and charts for cost, occupancy and assets",
        "app_name": "apex_habitat",
        "link": "/app/habitat-system-administration",
        "creation": "2026-03-20 09:05:00",
    },
    # [#309llc]
    {
        "title": "Apex Habitat v0.7.2 — faster reports, a fully translated interface, and security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-03-19 21:00:00",
    },
    {
        "title": "v0.7.2: Submit and cancel with confidence — your bills, checkouts and work orders stay consistent every time",
        "app_name": "apex_habitat",
        "link": "/app/utility-bill-entry",
        "creation": "2026-03-19 21:01:00",
    },
    {
        "title": "v0.7.2: Your clearance and cleaning reports open noticeably faster",
        "app_name": "apex_habitat",
        "link": "/app/checkout-pending-clearance",
        "creation": "2026-03-19 21:02:00",
    },
    {
        "title": "v0.7.2: Trust your numbers — occupancy and depreciation update live as your data changes",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-occupancy-summary",
        "creation": "2026-03-19 21:03:00",
    },
    {
        "title": "v0.7.2: Security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-room",
        "creation": "2026-03-19 21:04:00",
    },
    {
        "title": "v0.7.2: Work in Arabic end to end — the full interface is now translated",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-03-19 21:05:00",
    },
    # [#linbs0]
    {
        "title": "Apex Habitat v0.7.0 — a faster, sturdier build, plus a smarter building setup and lease payments",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-03-19 10:00:00",
    },
    {
        "title": "v0.7.0: Security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-03-19 10:01:00",
    },
    {
        "title": "v0.7.0: Book a bed with confidence — two people can claim the same bed at once and never collide",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-assignment",
        "creation": "2026-03-19 10:02:00",
    },
    {
        "title": "v0.7.0: Open the resident request form to the public safely — it stays protected against abuse",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-resident-request",
        "creation": "2026-03-19 10:03:00",
    },
    {
        "title": "v0.7.0: Catch operational warnings early — scheduler alerts now surface in the desk where you'll see them",
        "app_name": "apex_habitat",
        "link": "/app/habitat-operations-alert",
        "creation": "2026-03-19 10:04:00",
    },
    {
        "title": "v0.7.0: Run smoothly on big sites — scheduled jobs keep pace however much data you hold",
        "app_name": "apex_habitat",
        "link": "/app/habitat-settings",
        "creation": "2026-03-19 10:05:00",
    },
    {
        "title": "v0.7.0: Trust your daily cost — allocation lands accurately every day of the year, leap years included",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-ledger",
        "creation": "2026-03-19 10:06:00",
    },
    {
        "title": "v0.7.0: A sturdier foundation — every release now ships steadier and better tested",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-03-19 10:07:00",
    },
    {
        "title": "v0.7.0: Build a whole building in minutes — lay out floor after floor with the room generator and pick from nine room types",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-03-19 10:08:00",
    },
    {
        "title": "v0.7.0: Set up apartments as easily as buildings — choose the Apartment type and the floor fields step out of your way",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-03-19 10:09:00",
    },
    {
        "title": "v0.7.0: Pick a city from a ready list — 18 Saudi cities come built in and link straight to your buildings and sites",
        "app_name": "apex_habitat",
        "link": "/app/city",
        "creation": "2026-03-19 10:10:00",
    },
    {
        "title": "v0.7.0: Log every safety finding in one tidy list, right on the inspection report",
        "app_name": "apex_habitat",
        "link": "/app/safety-inspection-report",
        "creation": "2026-03-19 10:11:00",
    },
    {
        "title": "v0.7.0: Turn a lease into a payment in one click — generate a Payment Entry, Payment Order or Expense Request straight from the lease",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-lease",
        "creation": "2026-03-19 10:12:00",
    },
    {
        "title": "v0.7.0: A steadier core under the hood, so everything you build on it holds firm",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-03-19 10:13:00",
    },
    # [#hrf7ud]
    {
        "title": "Apex Habitat v0.6.0 — stock your maintenance catalog and set up a building from one screen",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-03-18 22:00:00",
    },
    {
        "title": "v0.6.0: Start maintenance with a ready-stocked shelf — 38 materials and 4 templates come built in",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-03-18 22:01:00",
    },
    {
        "title": "v0.6.0: Security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-03-18 22:02:00",
    },
    {
        "title": "v0.6.0: Set up a whole building without leaving the form — generate its rooms, beds and safety checklist with a tap",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-03-18 22:03:00",
    },
    {
        "title": "Apex Habitat v0.5.0 — give every building a safety checklist in one tap",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-03-18 18:00:00",
    },
    {
        "title": "v0.5.0: Stand up a building's safety setup instantly and track its readiness right on the form",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-03-18 18:01:00",
    },
    {
        "title": "Apex Habitat v0.4.0 — set up accommodation in bulk and get every room ready",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-03-18 00:00:00",
    },
    {
        "title": "v0.4.0: Lay out a floor plan and generate all its rooms and beds at once — no more one-by-one entry",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-03-18 00:01:00",
    },
    {
        "title": "v0.4.0: Track each room's readiness and jot supervisor inventory notes as you go",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-room",
        "creation": "2026-03-18 00:02:00",
    },
    {
        "title": "v0.4.0: Print a tidy label for every room in a click",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-room",
        "creation": "2026-03-18 00:03:00",
    },
    {
        "title": "v0.3.1: Track assets moving between companies, and jump to any report from eight new shortcuts",
        "app_name": "apex_habitat",
        "link": "/app/facility-asset-movement",
        "creation": "2026-03-15 00:00:00",
    },
    {
        "title": "v0.3.0: Work by company, link employees to their housing, and reach for five new operational reports",
        "app_name": "apex_habitat",
        "link": "/app/habitat-settings",
        "creation": "2026-03-13 00:00:00",
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
