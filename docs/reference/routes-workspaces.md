# Modules, Workspaces, and Routes

<!-- Generated from the shipped modules.txt, Workspace JSON, Page JSON and www/
     templates. Do not edit by hand; edit the app and regenerate. -->

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
| **Apex** | Apex Core | — (root) | `1.0` | — |
| **Apex Core** | Apex Core | Apex | `2.0` | System Manager |
| **Housing and Safety** | Habitat | Habitat | `2.1` | Accommodation Manager, Cleaning Supervisor, Internal Auditor, Maintenance Technician, Resident Supervisor, Safety Officer, System Manager |
| **Custody and Costs** | Habitat | Habitat | `2.2` | Accommodation Manager, Finance Manager, Resident Supervisor, SIM Operations User, System Manager |
| **Salis** | Salis | Apex | `3.0` | Finance Manager, Fleet Manager, Fleet Project Manager, Fleet Supervisor, Government Relations Officer, Internal Auditor, System Manager |
| **Fleet** | Salis | Salis | `3.3` | Fleet Manager, Fleet Project Manager, Fleet Supervisor, System Manager |
| **Habitat** | Habitat | Apex | `4.0` | Accommodation Manager, Administrator, Cleaning Supervisor, Finance Manager, Fleet Manager, Internal Auditor, Maintenance Technician, Resident Supervisor, SIM Operations User, Safety Officer, System Manager |
| **Logistay** | Logistay | Apex | `5.0` | Administrator, SIM Operations User, System Manager |
| **My Tasks** | Apex Core | Apex | `6.0` | — |

An em dash under Roles means the Workspace JSON declares no role rows, so the
workspace is visible to every signed-in user. Visibility is not access.

## Desk pages

Apex ships **eleven** Desk pages.

| Desk page | Route | Module | Roles |
|---|---|---|---|
| **Action Inbox** | `/app/action-inbox` | Apex Core | — |
| **Arrivals Desk** | `/app/arrivals-desk` | Habitat | Accommodation Manager, Resident Supervisor, System Manager |
| **Custody Kiosk** | `/app/custody-kiosk` | Habitat | Accommodation Manager, Resident Supervisor, System Manager |
| **Front Desk** | `/app/front-desk` | Habitat | Accommodation Manager, Resident Supervisor, System Manager |
| **Fuel Approval Console** | `/app/fuel-approval-console` | Salis | Finance Manager, Fleet Manager, Fleet Project Manager, System Manager |
| **Fleet Control** | `/app/operations-control` | Salis | Fleet Manager, Fleet Project Manager, Fleet Supervisor, System Manager |
| **Room Setup** | `/app/room-setup` | Habitat | Accommodation Manager, System Manager |
| **Safety Map** | `/app/safety-map` | Habitat | Accommodation Manager, Resident Supervisor, System Manager |
| **Salis Dispatch Board** | `/app/salis-dispatch-board` | Salis | Fleet Manager, Fleet Project Manager, Fleet Supervisor, System Manager |
| **Telecom Control** | `/app/telecom-control` | Logistay | SIM Operations User, System Manager |
| **Transfer Board** | `/app/transfer-board` | Habitat | Accommodation Manager, System Manager |

An em dash means the Page JSON declares no Page-role rows; it does not mean
guest access. A Page role controls entry only. Its APIs and source records must
still enforce DocPerm, workflow, identity, and row scope.

## Workspace portal shortcuts

| Workspace | Shortcut label | URL |
|---|---|---|
| Apex | `Fleet OS` | `/fleet-os` |
| Apex | `Housing Inventory Count` | `/housing-count` |
| Apex | `Housing Portal` | `/housing` |
| Apex | `Masar` | `/masar` |
| Apex | `Masar Supervisor` | `/masar-supervisor` |
| Apex | `My Fleet` | `/fleet` |
| Apex | `Safety Rounds` | `/safety` |
| Apex | `Salis Driver` | `/driver` |
| Fleet | `Fleet OS` | `/fleet-os` |
| Fleet | `Masar Supervisor` | `/masar-supervisor` |
| Housing and Safety | `Housing Portal` | `/housing` |
| Housing and Safety | `Inventory Count` | `/housing-count` |
| Housing and Safety | `Safety Checklist` | `/safety` |
| Salis | `Worker Route (Masar)` | `/masar` |

## Served portal routes

Apex answers **eight** addresses under `apex/www/`: **seven** portal shells
that mount a bundle, and one that mounts none and only redirects. Routing is
pure `www/` file convention: the route is the template name, and the
controller is that name with hyphens turned into underscores.

| Route | Audience | Authentication path | Controller · bundle |
|---|---|---|---|
| `/driver` | Drivers | Guest-accessible personal token; identity is resolved server-side. | `apex/www/driver.py` · `worker_portal` |
| `/fleet-os` | Fleet supervisors | Guest redirect, then `FLEET_ROLES`: Fleet Manager, Fleet Project Manager, Fleet Supervisor, System Manager. | `apex/www/fleet_os.py` · `fleet_os_portal` |
| `/fleet` | Signed-in employees | Guest redirect, then no role gate; endpoints scope data to the signed-in user. | `apex/www/fleet.py` · `fleet_portal` |
| `/housing-count` | Accommodation operators | Redirects to `/housing#/count`; the target enforces the gate. | `apex/www/housing_count.py` · — |
| `/housing` | Accommodation operators | Guest redirect, then `HOUSING_ROLES`: Accommodation Manager, Procurement Supervisor, Resident Supervisor, System Manager. | `apex/www/housing.py` · `housing_portal` |
| `/masar-supervisor` | Route supervisors | Guest redirect, then `SUPERVISOR_ROLES`: Fleet Manager, Fleet Project Manager, Fleet Supervisor, System Manager. | `apex/www/masar_supervisor.py` · `route_supervisor_portal` |
| `/masar` | Workers | Guest-accessible personal token; identity is resolved server-side. | `apex/www/masar.py` · `worker_portal` |
| `/safety` | Safety supervisors | Guest redirect, then `SAFETY_ROLES`: Accommodation Manager, Resident Supervisor, System Manager. | `apex/www/safety.py` · `safety_portal` |

The route gate is only the entry check. Each API must enforce document
permission and row scope independently.
