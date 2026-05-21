# Apex Habitat

Accommodation and facilities management application for **Frappe Framework v15**.

## Module

Single module: **Habitat** — all DocTypes, reports, and scheduled tasks are registered under this module.

## Architecture

This app follows a multi-layer layout:

- **Controllers**: `habitat/doctype/**` — 32 DocType controllers covering Phases 1–7
- **Services**: `habitat/services/**` — business logic and orchestration (base class only)
- **Repositories**: `habitat/repositories/**` — data access and persistence helpers (base class only)
- **API**: `habitat/api/**` — whitelisted endpoints and REST handlers
- **Scheduled Tasks**: `habitat/tasks.py` — 5 daily, 2 weekly, 1 monthly jobs

## DocType Phases

| Phase | Scope | DocTypes |
|-------|-------|----------|
| 1 | Settings | Habitat Settings (Single) |
| 2 | Spatial Master Data | Accommodation Site, Building, Room, Bed |
| 3 | Occupancy Lifecycle | Assignment, Checkout, Room Bed Transfer, Custody Items |
| 4 | Financial Layer | Ledger, Utility Account, Utility Bill Entry, Lease, Rent Schedule |
| 5 | Custody and Depreciation | Custody Asset Category, Article, Issue, Return, Damage, Depreciation |
| 6 | Asset and Maintenance | Facility Asset Movement, Maintenance Work Order |
| 7 | Scheduling and Inspection | Scheduled Task Template/Instance, Inspection Report, Findings |


