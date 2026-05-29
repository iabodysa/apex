from frappe.utils import get_datetime

# Static release feed for Apex Habitat.
# Each entry has: title, app_name, link, creation (ISO datetime string).
# creation must be a fixed past timestamp so deduplication is stable across repeated calls.
# fetch_changelog_feed() checks frappe.db.exists("Changelog Feed", {title, app_name, link, posting_timestamp})
# before inserting — fully idempotent.

_RELEASES = [
    # v1.6.0 ----------------------------------------------------------------
    {
        "title": "Apex 1.6.0 — shared settings now live together in one Apex Core area",
        "app_name": "apex_habitat",
        "link": "/app/apex-core",
        "creation": "2026-06-18 09:00:00",
    },
    # v1.5.0 ----------------------------------------------------------------
    {
        "title": "Apex 1.5.0 — connected records everywhere, a Salis getting-started guide, and cleaner navigation",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-17 09:00:00",
    },
    {
        "title": "v1.5.0: Open a record and see everything related to it in the Connections tab — across vehicles, drivers, custody, maintenance, leases and more",
        "app_name": "apex_habitat",
        "link": "/app/salis-vehicle",
        "creation": "2026-06-17 09:01:00",
    },
    {
        "title": "v1.5.0: A new Salis 'Go-Live' guide walks you through your first vehicle, driver, assignment and trip",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-17 09:02:00",
    },
    {
        "title": "v1.5.0: Reach your Salis dashboards and trend charts straight from the workspace, with shorter, clearer area names",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-17 09:03:00",
    },
    {
        "title": "v1.5.0: Optional email templates and scheduled email reports for the Movement team, plus reliability and tidiness improvements",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-17 09:04:00",
    },
    # v1.4.1 ----------------------------------------------------------------
    {
        "title": "Apex 1.4.1 — security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-16 09:00:00",
    },
    # v1.4.0 ----------------------------------------------------------------
    {
        "title": "Apex 1.4.0 — Movement costs now carry Company and Cost Center, with quicker navigation",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-15 09:00:00",
    },
    {
        "title": "v1.4.0: Rentals, fuel claims, payments and cost recoveries now record their Company and Cost Center — so finance can filter and group Movement costs cleanly",
        "app_name": "apex_habitat",
        "link": "/app/rental-settlement",
        "creation": "2026-06-15 09:01:00",
    },
    {
        "title": "v1.4.0: Salis areas have short, clear names and a Help-menu shortcut, so you reach the Dispatch Board and your work area in one click",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-15 09:02:00",
    },
    # v1.3.0 ----------------------------------------------------------------
    {
        "title": "Apex 1.3.0 — quicker Salis navigation, one-tap record creation and a leaner role setup",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-14 09:00:00",
    },
    {
        "title": "v1.3.0: Jump straight to the area you work in — Workers Transport, Representatives Fleet, Fuel, Rentals, Compliance and Setup",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-14 09:01:00",
    },
    {
        "title": "v1.3.0: Create as you go — new driver, vehicle, trip or fuel request right from each Salis area",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-14 09:02:00",
    },
    {
        "title": "v1.3.0: A simpler set of roles that fits a focused team, plus security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-14 09:03:00",
    },
    # v1.2.0 ----------------------------------------------------------------
    {
        "title": "Apex 1.2.0 — Salis gets a live dispatch board, deeper dashboards, printable documents and smarter alerts",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-13 09:00:00",
    },
    {
        "title": "v1.2.0: A new Dispatch Board shows your fleet, today's trips and which drivers are free — all on one screen",
        "app_name": "apex_habitat",
        "link": "/app/salis-dispatch-board",
        "creation": "2026-06-13 09:01:00",
    },
    {
        "title": "v1.2.0: Print clean handover receipts, fuel vouchers, rental settlement statements and driver clearance certificates",
        "app_name": "apex_habitat",
        "link": "/app/vehicle-handover",
        "creation": "2026-06-13 09:02:00",
    },
    {
        "title": "v1.2.0: New reports at your fingertips — vehicle utilisation, fuel spend by vehicle, rental cost by office, fulfilment SLA and recovery aging",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-13 09:03:00",
    },
    {
        "title": "v1.2.0: Salis now reaches out — alerts for expiring compliance, blocked clearances and overdue fuel, and it routes new work to the right person",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-13 09:04:00",
    },
    {
        "title": "v1.2.0: Find your way by area — Workers Transport, Representatives Fleet, Fuel, Rentals, Compliance and Setup each get their own space",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-13 09:05:00",
    },
    # v1.1.1 ----------------------------------------------------------------
    {
        "title": "Apex 1.1.1 — security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-12 09:00:00",
    },
    # v1.1.0 ----------------------------------------------------------------
    {
        "title": "Apex 1.1.0 — Salis opens to the numbers that matter, on a cleaner two-division workspace",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-11 09:00:00",
    },
    {
        "title": "v1.1.0: See your fleet at a glance — active vehicles, vehicles in the shop, open transport requests and pending approvals greet you the moment Salis opens",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-11 09:01:00",
    },
    {
        "title": "v1.1.0: Read status at a glance — colour-coded vehicles, drivers, trips, fuel, maintenance and accommodation, everywhere you look (list, Kanban, Calendar and Report)",
        "app_name": "apex_habitat",
        "link": "/app/salis-vehicle",
        "creation": "2026-06-11 09:02:00",
    },
    # v1.0.1 ----------------------------------------------------------------
    {
        "title": "Apex 1.0.1 — security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-06-10 09:00:00",
    },
    # v1.0.0 stable -------------------------------------------------------
    {
        "title": "Apex 1.0.0 — your workforce operations, end to end: where they live and how they move, now in one suite",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-06-09 09:00:00",
    },
    # v1.0.0 ----------------------------------------------------------
    {
        "title": "v1.0.0: Meet Salis — take command of every vehicle, driver, trip and litre of fuel from one Movement workspace",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-08 09:00:00",
    },
    {
        "title": "v1.0.0: Run both sides of Movement from one place — shuttle workers from camp to site and across cities, and keep your representatives' cars, trips and fuel on track",
        "app_name": "apex_habitat",
        "link": "/app/transport-request",
        "creation": "2026-06-08 09:01:00",
    },
    {
        "title": "v1.0.0: Every fuel, transport and transfer request finds the right approver automatically — small ones clear fast, big ones escalate up the chain on their own",
        "app_name": "apex_habitat",
        "link": "/app/approval-request",
        "creation": "2026-06-08 09:02:00",
    },
    {
        "title": "v1.0.0: Clear pending fuel requests in seconds from the Fuel Approval Console, and settle any disputed fuel cleanly with an evidence-backed exception case",
        "app_name": "apex_habitat",
        "link": "/app/fuel-approval-console",
        "creation": "2026-06-08 09:03:00",
    },
    {
        "title": "v1.0.0: Watch rental costs add up day by day, close the month with one Rental Settlement, and hand finance a ready-to-pay request",
        "app_name": "apex_habitat",
        "link": "/app/rental-settlement",
        "creation": "2026-06-08 09:04:00",
    },
    {
        "title": "v1.0.0: Put the Driver Portal in every driver's pocket — check in, see today's trips, request fuel and raise a ticket from a phone at /driver",
        "app_name": "apex_habitat",
        "link": "/driver",
        "creation": "2026-06-08 09:05:00",
    },
    {
        "title": "v1.0.0: Open any Employee or Supplier and see their Movement story right there — driver record, trips and rental activity, one click away",
        "app_name": "apex_habitat",
        "link": "/app/salis",
        "creation": "2026-06-08 09:06:00",
    },
    # v0.9.1 ---------------------------------------------------------------
    {
        "title": "Apex Habitat v0.9.1 — guided setup is back, and every record shows what it's connected to",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-06-06 09:30:00",
    },
    {
        "title": "v0.9.1: Never wonder where to start — step-by-step setup banners now guide you through Setup, Accommodation and Safety",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-06-06 09:31:00",
    },
    {
        "title": "v0.9.1: Open a building and see its whole world in one tab — rooms, beds, residents, leases, custody and more, all one click away",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-06-06 09:32:00",
    },
    # v0.9.0 ---------------------------------------------------------------
    {
        "title": "v0.9.0: Stop typing, start tapping — move residents, inspect rooms and issue gear from fast, visual boards",
        "app_name": "apex_habitat",
        "link": "/app/transfer-board",
        "creation": "2026-06-04 09:00:00",
    },
    {
        "title": "v0.9.0: Move a resident between buildings with a single drag — pull one bed onto another and you're done",
        "app_name": "apex_habitat",
        "link": "/app/transfer-board",
        "creation": "2026-06-04 09:01:00",
    },
    {
        "title": "v0.9.0: Walk your buildings on a live Safety Map — rooms needing attention pulse for you; tap one to log an inspection on the spot",
        "app_name": "apex_habitat",
        "link": "/app/safety-map",
        "creation": "2026-06-04 09:02:00",
    },
    {
        "title": "v0.9.0: Hand out custody like a checkout counter — tap big item tiles into a cart and issue, all from the Custody Kiosk",
        "app_name": "apex_habitat",
        "link": "/app/custody-kiosk",
        "creation": "2026-06-04 09:03:00",
    },
    {
        "title": "v0.9.0: Check in the right person every time — Front Desk now shows the worker's photo and saves a room-condition snapshot at handover",
        "app_name": "apex_habitat",
        "link": "/app/front-desk",
        "creation": "2026-06-04 09:04:00",
    },
    # v0.8.6 ---------------------------------------------------------------
    {
        "title": "Apex Habitat v0.8.6 — check residents in and out from a visual board, and never lose track of an idle worker",
        "app_name": "apex_habitat",
        "link": "/app/front-desk",
        "creation": "2026-05-26 09:00:00",
    },
    {
        "title": "v0.8.6: Run the front desk by colour — tap a green bed to check someone in, a red bed to check them out",
        "app_name": "apex_habitat",
        "link": "/app/front-desk",
        "creation": "2026-05-26 09:01:00",
    },
    {
        "title": "v0.8.6: Resident Supervisors can now check residents in and out themselves, right from the Front Desk board",
        "app_name": "apex_habitat",
        "link": "/app/front-desk",
        "creation": "2026-05-26 09:02:00",
    },
    {
        "title": "v0.8.6: Stop paying for forgotten workers — flag an idle resident and Apex routes a follow-up to the right team and counts the days and the cost for you",
        "app_name": "apex_habitat",
        "link": "/app/idle-resident-report",
        "creation": "2026-05-26 09:03:00",
    },
    # v0.8.5 ---------------------------------------------------------------
    {
        "title": "Apex Habitat v0.8.5 — book short stays with a clear end date, and start holding idle workers to account",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-assignment",
        "creation": "2026-05-25 21:00:00",
    },
    {
        "title": "v0.8.5: Book a stay as permanent or temporary and set an expected check-out date, so short stays never quietly become permanent",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-assignment",
        "creation": "2026-05-25 21:01:00",
    },
    {
        "title": "v0.8.5: Catch a stay before it overruns — a daily watchlist flags temporary residents nearing or past their check-out date",
        "app_name": "apex_habitat",
        "link": "/app/habitat-settings",
        "creation": "2026-05-25 21:02:00",
    },
    {
        "title": "v0.8.5: Spotlight workers living in camp but not yet deployed, and put a name to who owns getting them moving",
        "app_name": "apex_habitat",
        "link": "/app/idle-resident-report",
        "creation": "2026-05-25 21:03:00",
    },
    # v0.8.4 ---------------------------------------------------------------
    {
        "title": "Apex Habitat v0.8.4 — let the right reports, reminders and follow-ups send themselves",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-25 18:00:00",
    },
    {
        "title": "v0.8.4: Have your key reports land in inboxes on schedule — supplier cost recovery, occupancy trend, maintenance backlog and task compliance, sent automatically once you turn them on",
        "app_name": "apex_habitat",
        "link": "/app/auto-email-report",
        "creation": "2026-05-25 18:01:00",
    },
    {
        "title": "v0.8.4: Send polished renewal and acknowledgement emails in a click, with ready-made templates for licences, leases and resident requests",
        "app_name": "apex_habitat",
        "link": "/app/email-template",
        "creation": "2026-05-25 18:02:00",
    },
    {
        "title": "v0.8.4: Nothing slips through the cracks — assigning a resident request drops a follow-up into that person's to-do list, and closing the request ticks it off",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-resident-request",
        "creation": "2026-05-25 18:03:00",
    },
    {
        "title": "v0.8.4: Jump straight to the Command Center or Setup from the Help menu — your key workspaces are always one click away",
        "app_name": "apex_habitat",
        "link": "/app/operations-command-center",
        "creation": "2026-05-25 18:04:00",
    },
    # v0.8.3 ---------------------------------------------------------------
    {
        "title": "Apex Habitat v0.8.3 — see your work on a calendar, move it across a board, and let it route itself",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-25 15:00:00",
    },
    {
        "title": "v0.8.3: See what's due on a calendar — scheduled tasks, licence and lease dates, and service orders, laid out by date",
        "app_name": "apex_habitat",
        "link": "/app/scheduled-task-instance/view/calendar",
        "creation": "2026-05-25 15:01:00",
    },
    {
        "title": "v0.8.3: Turn rooms around faster — drag each room from Needs Cleaning to Ready on a housekeeping board",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-room/view/kanban",
        "creation": "2026-05-25 15:02:00",
    },
    {
        "title": "v0.8.3: Let new maintenance and resident requests assign themselves to your team — just add your people and switch it on",
        "app_name": "apex_habitat",
        "link": "/app/assignment-rule",
        "creation": "2026-05-25 15:03:00",
    },
    {
        "title": "v0.8.3: Keep your team in the loop automatically — opt-in alerts when a request is assigned, raised, waiting on evidence, or carries a damage assessment",
        "app_name": "apex_habitat",
        "link": "/app/notification",
        "creation": "2026-05-25 15:04:00",
    },
    # v0.8.2 ---------------------------------------------------------------
    {
        "title": "Apex Habitat v0.8.2 — every building becomes its own store, with stock you can track and move",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-stock-ledger",
        "creation": "2026-05-25 12:00:00",
    },
    {
        "title": "v0.8.2: Always know what's in each building — issue and return custody and watch stock move in and out, item by item",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-stock-ledger",
        "creation": "2026-05-25 12:01:00",
    },
    {
        "title": "v0.8.2: Send supplies between buildings with confidence — ship a transfer, mark it received on arrival, and never move more than a store actually holds",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-material-transfer",
        "creation": "2026-05-25 12:02:00",
    },
    {
        "title": "v0.8.2: Keep finance in the picture — moving stock across cost centres sends them a heads-up memo, automatically",
        "app_name": "apex_habitat",
        "link": "/app/habitat-settings",
        "creation": "2026-05-25 12:03:00",
    },
    {
        "title": "v0.8.2: Know exactly what you have and what it's worth — on-hand quantity and value for every store and every employee's custody, in one report",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-stock-balance/view/report",
        "creation": "2026-05-25 12:04:00",
    },
    {
        "title": "v0.8.2: Triage at a glance — drag resident and maintenance requests across status columns on their own boards",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-resident-request/view/kanban",
        "creation": "2026-05-25 12:05:00",
    },
    # v0.8.0 ---------------------------------------------------------------
    {
        "title": "Apex Habitat v0.8.0 — bill suppliers back, see occupancy trends, and print every handover",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-25 09:00:00",
    },
    {
        "title": "v0.8.0: Recover what suppliers' workers cost you — a monthly report totals each supplier's housing cost and adds your markup, ready to bill",
        "app_name": "apex_habitat",
        "link": "/app/supplier-cost-recovery/view/report",
        "creation": "2026-05-25 09:01:00",
    },
    {
        "title": "v0.8.0: Get expiry and overdue alerts right where you work — posted on the document's own timeline and, if you like, straight to your inbox",
        "app_name": "apex_habitat",
        "link": "/app/habitat-settings",
        "creation": "2026-05-25 09:02:00",
    },
    {
        "title": "v0.8.0: See how full your buildings have been over time — a new Occupancy Trend report charts the lows, averages, highs and days over capacity",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-occupancy-snapshot",
        "creation": "2026-05-25 09:03:00",
    },
    {
        "title": "v0.8.0: Print a signed handover in seconds — bilingual receipts for custody issue and return, checkout clearance, damage notices and work orders",
        "app_name": "apex_habitat",
        "link": "/app/custody-issue",
        "creation": "2026-05-25 09:04:00",
    },
    {
        "title": "v0.8.0: Keep an eye on the whole operation from one System Administration workspace, with fresh cards and charts for cost, occupancy and assets",
        "app_name": "apex_habitat",
        "link": "/app/habitat-system-administration",
        "creation": "2026-05-25 09:05:00",
    },
    # v0.7.2 ---------------------------------------------------------------
    {
        "title": "Apex Habitat v0.7.2 — faster reports, a fully translated interface, and security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-24 21:00:00",
    },
    {
        "title": "v0.7.2: Submit and cancel with confidence — your bills, checkouts and work orders stay consistent every time",
        "app_name": "apex_habitat",
        "link": "/app/utility-bill-entry",
        "creation": "2026-05-24 21:01:00",
    },
    {
        "title": "v0.7.2: Your clearance and cleaning reports open noticeably faster",
        "app_name": "apex_habitat",
        "link": "/app/checkout-pending-clearance",
        "creation": "2026-05-24 21:02:00",
    },
    {
        "title": "v0.7.2: Trust your numbers — occupancy and depreciation update live as your data changes",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-occupancy-summary",
        "creation": "2026-05-24 21:03:00",
    },
    {
        "title": "v0.7.2: Security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-room",
        "creation": "2026-05-24 21:04:00",
    },
    {
        "title": "v0.7.2: Work in Arabic end to end — the full interface is now translated",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-24 21:05:00",
    },
    # v0.7.0 ---------------------------------------------------------------
    {
        "title": "Apex Habitat v0.7.0 — a faster, sturdier build, plus a smarter building setup and lease payments",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-05-24 10:00:00",
    },
    {
        "title": "v0.7.0: Security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-24 10:01:00",
    },
    {
        "title": "v0.7.0: Book a bed with confidence — two people can claim the same bed at once and never collide",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-assignment",
        "creation": "2026-05-24 10:02:00",
    },
    {
        "title": "v0.7.0: Open the resident request form to the public safely — it stays protected against abuse",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-resident-request",
        "creation": "2026-05-24 10:03:00",
    },
    {
        "title": "v0.7.0: Catch operational warnings early — scheduler alerts now surface in the desk where you'll see them",
        "app_name": "apex_habitat",
        "link": "/app/habitat-operations-alert",
        "creation": "2026-05-24 10:04:00",
    },
    {
        "title": "v0.7.0: Run smoothly on big sites — scheduled jobs keep pace however much data you hold",
        "app_name": "apex_habitat",
        "link": "/app/habitat-settings",
        "creation": "2026-05-24 10:05:00",
    },
    {
        "title": "v0.7.0: Trust your daily cost — allocation lands accurately every day of the year, leap years included",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-ledger",
        "creation": "2026-05-24 10:06:00",
    },
    {
        "title": "v0.7.0: A sturdier foundation — every release now ships steadier and better tested",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-24 10:07:00",
    },
    {
        "title": "v0.7.0: Build a whole building in minutes — lay out floor after floor with the room generator and pick from nine room types",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-05-24 10:08:00",
    },
    {
        "title": "v0.7.0: Set up apartments as easily as buildings — choose the Apartment type and the floor fields step out of your way",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-05-24 10:09:00",
    },
    {
        "title": "v0.7.0: Pick a city from a ready list — 18 Saudi cities come built in and link straight to your buildings and sites",
        "app_name": "apex_habitat",
        "link": "/app/city",
        "creation": "2026-05-24 10:10:00",
    },
    {
        "title": "v0.7.0: Log every safety finding in one tidy list, right on the inspection report",
        "app_name": "apex_habitat",
        "link": "/app/safety-inspection-report",
        "creation": "2026-05-24 10:11:00",
    },
    {
        "title": "v0.7.0: Turn a lease into a payment in one click — generate a Payment Entry, Payment Order or Expense Request straight from the lease",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-lease",
        "creation": "2026-05-24 10:12:00",
    },
    {
        "title": "v0.7.0: A steadier core under the hood, so everything you build on it holds firm",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-24 10:13:00",
    },
    # v0.6.0 ---------------------------------------------------------------
    {
        "title": "Apex Habitat v0.6.0 — stock your maintenance catalog and set up a building from one screen",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-23 22:00:00",
    },
    {
        "title": "v0.6.0: Start maintenance with a ready-stocked shelf — 38 materials and 4 templates come built in",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-23 22:01:00",
    },
    {
        "title": "v0.6.0: Security & reliability improvements",
        "app_name": "apex_habitat",
        "link": "/app/setup",
        "creation": "2026-05-23 22:02:00",
    },
    {
        "title": "v0.6.0: Set up a whole building without leaving the form — generate its rooms, beds and safety checklist with a tap",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-05-23 22:03:00",
    },
    {
        "title": "Apex Habitat v0.5.0 — give every building a safety checklist in one tap",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-05-23 18:00:00",
    },
    {
        "title": "v0.5.0: Stand up a building's safety setup instantly and track its readiness right on the form",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-05-23 18:01:00",
    },
    {
        "title": "Apex Habitat v0.4.0 — set up accommodation in bulk and get every room ready",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-05-23 00:00:00",
    },
    {
        "title": "v0.4.0: Lay out a floor plan and generate all its rooms and beds at once — no more one-by-one entry",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-building",
        "creation": "2026-05-23 00:01:00",
    },
    {
        "title": "v0.4.0: Track each room's readiness and jot supervisor inventory notes as you go",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-room",
        "creation": "2026-05-23 00:02:00",
    },
    {
        "title": "v0.4.0: Print a tidy label for every room in a click",
        "app_name": "apex_habitat",
        "link": "/app/accommodation-room",
        "creation": "2026-05-23 00:03:00",
    },
    {
        "title": "v0.3.1: Track assets moving between companies, and jump to any report from eight new shortcuts",
        "app_name": "apex_habitat",
        "link": "/app/facility-asset-movement",
        "creation": "2026-05-20 00:00:00",
    },
    {
        "title": "v0.3.0: Work by company, link employees to their housing, and reach for five new operational reports",
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
