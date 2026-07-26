# Modules, Workspaces, and Routes

This page is the canonical public reference for Apex modules, Desk workspaces,
Desk pages, workspace portal shortcuts, and served portal routes. Navigation
makes a surface discoverable; DocPerm, workflow, and server-side row scope
control its data.

## Modules

`apex/modules.txt` declares **four** names, one per bullet below:

- **Habitat** — accommodation, facilities, custody, safety, maintenance, and facility costs.
- **Salis** — movement, fleet, fuel, dispatch, rentals, and transport operations.
- **Apex Core** — shared settings, setup, permissions, notifications, and portal security.
- **Logistay** — workforce and telecom contracts, SIM inventory, custody, billing, and reporting.

## Workspaces

| Workspace | Module | Parent | `sequence_id` | Roles |
|---|---|---|---|---|
| **Habitat** | Habitat | — (root) | `2.0` | Accommodation Manager, Finance Manager, Resident Supervisor, Cleaning Supervisor, Safety Officer, Maintenance Technician, Internal Auditor, SIM Operations User, System Manager, Fleet Manager, Administrator |
| **Housing** | Habitat | Habitat | `2.1` | Accommodation Manager, Cleaning Supervisor, Resident Supervisor, System Manager |
| **Safety** | Habitat | Habitat | `2.2` | Accommodation Manager, Resident Supervisor, Safety Officer, Maintenance Technician, Cleaning Supervisor, Internal Auditor, System Manager |
| **Custody** | Habitat | Habitat | `2.3` | Accommodation Manager, Resident Supervisor, SIM Operations User, System Manager |
| **Costs and Leasing** | Habitat | Habitat | `2.4` | Finance Manager, Accommodation Manager, System Manager |
| **Salis** | Salis | — (root) | `3.0` | Finance Manager, Fleet Manager, Fleet Project Manager, Fleet Supervisor, Government Relations Officer, Internal Auditor, System Manager |
| **Compliance and Rentals** | Salis | Salis | `3.2` | Fleet Manager, Fleet Supervisor, Finance Manager, Government Relations Officer, Internal Auditor, System Manager |
| **Fleet** | Salis | Salis | `4.0` | Fleet Manager, Fleet Project Manager, Fleet Supervisor, System Manager |
| **Backend Engines** | Habitat | — (root, `is_hidden`) | `90.1` | System Manager |

Backend Engines is hidden because it exposes system-written ledgers and
snapshots. Logistay uses the Telecom Control Desk page and places its navigation
on Custody instead of shipping another workspace.

## Desk pages

Apex ships **eleven** Desk pages.

| Desk page | Route | Module | Roles |
|---|---|---|---|
| **Action Inbox** | `/app/action-inbox` | Apex Core | — |
| **Arrivals Desk** | `/app/arrivals-desk` | Habitat | System Manager, Accommodation Manager, Resident Supervisor |
| **Custody Kiosk** | `/app/custody-kiosk` | Habitat | System Manager, Accommodation Manager, Resident Supervisor |
| **Front Desk** | `/app/front-desk` | Habitat | System Manager, Accommodation Manager, Resident Supervisor |
| **Room Setup** | `/app/room-setup` | Habitat | System Manager, Accommodation Manager |
| **Safety Map** | `/app/safety-map` | Habitat | System Manager, Accommodation Manager, Resident Supervisor |
| **Transfer Board** | `/app/transfer-board` | Habitat | System Manager, Accommodation Manager |
| **Telecom Control** | `/app/telecom-control` | Logistay | SIM Operations User, System Manager |
| **Fuel Approval Console** | `/app/fuel-approval-console` | Salis | System Manager, Fleet Manager, Fleet Project Manager, Finance Manager |
| **Fleet Control** | `/app/operations-control` | Salis | System Manager, Fleet Manager, Fleet Project Manager, Fleet Supervisor |
| **Salis Dispatch Board** | `/app/salis-dispatch-board` | Salis | System Manager, Fleet Manager, Fleet Project Manager, Fleet Supervisor |

An em dash means the Page JSON declares no Page-role rows; it does not mean
guest access. A Page role controls entry only. Its APIs and source records must
still enforce DocPerm, workflow, identity, and row scope.

## Workspace portal shortcuts

| Workspace | Shortcut label | URL | Portal it opens |
|---|---|---|---|
| Fleet | `Fleet OS` | `/fleet-os` | Fleet supervisor board |
| Fleet | `Masar Supervisor` | `/masar-supervisor` | Route dispatch board |
| Housing | `Housing Portal` | `/housing` | Housing operator portal |
| Housing | `Inventory Count` | `/housing-count` | Housing inventory count view |
| Safety | `Safety Checklist` | `/safety` | Safety operator portal |
| Salis | `Worker Route (Masar)` | `/masar` | Worker self-service view |

## Served portal routes

Apex serves **seven** portal routes.

| Route | Audience | Authentication path | Controller · bundle |
|---|---|---|---|
| `/driver` | Drivers | Guest-accessible personal token; identity is resolved server-side. | `apex/www/driver.py` · `worker_portal` |
| `/masar` | Workers | Guest-accessible personal token; identity is resolved server-side. | `apex/www/masar.py` · `worker_portal` |
| `/fleet` | Signed-in employees | Guest redirect, then no role gate; endpoints scope data to the signed-in employee. | `apex/www/fleet.py` · `fleet_portal` |
| `/fleet-os` | Fleet supervisors | Guest redirect, then `FLEET_ROLES`: System Manager, Fleet Manager, Fleet Project Manager, Fleet Supervisor. | `apex/www/fleet_os.py` · `fleet_os_portal` |
| `/housing` | Accommodation operators | Guest redirect, then `HOUSING_ROLES`: System Manager, Accommodation Manager, Resident Supervisor, Procurement Supervisor. | `apex/www/housing.py` · `housing_portal` |
| `/safety` | Safety supervisors | Guest redirect, then `SAFETY_ROLES`: System Manager, Accommodation Manager, Resident Supervisor. | `apex/www/safety.py` · `safety_portal` |
| `/masar-supervisor` | Route supervisors | Guest redirect, then `SUPERVISOR_ROLES`: System Manager, Fleet Manager, Fleet Project Manager, Fleet Supervisor. | `apex/www/masar_supervisor.py` · `route_supervisor_portal` |

The route gate is only the entry check. Each API must enforce document
permission and row scope independently.
