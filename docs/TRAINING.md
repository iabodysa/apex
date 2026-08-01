# Apex Training Guide

The Apex training guide is organised as a set of focused, per-area pages under
[`docs/training/`](training/README.md). Each page covers one functional area with
its DocTypes, roles and permissions, key fields, and typical workflow.

**Start here: [Training Guide Index](training/README.md)**

## Quick links

### Habitat
- [Accommodation](training/accommodation.md)
- [Custody](training/custody.md)
- [Safety](training/safety.md)
- [Maintenance](training/maintenance.md)
- [Costs (Facilities & Utilities)](training/costs.md)

### Salis (Movement & Fleet)
- [Fleet & Compliance](training/fleet-movement.md)
- [Fuel](training/fuel.md)
- [Rentals](training/rentals.md)
- [Payments & Approvals (Segregation of Duties)](training/compliance.md)

### Portals & Shared
- [Driver & Worker (Masar) Portals](training/portals-masar-driver.md) — the two
  personal-link self-service apps, `/driver` and `/masar`
- [Settings & Desk Pages](training/settings.md)

> Apex serves **seven** portal routes in total. Besides the two self-service apps
> above, five are session- and role-gated operator surfaces: `/fleet` (employee
> self-service), `/fleet-os` (fleet supervisor board), `/housing`, `/safety`, and
> `/masar-supervisor` (route supervisor). Every route, its audience, and its
> authentication path are listed once in
> [Served portal routes](../README.md#served-portal-routes).

> Screens are marked with `_[screenshot: ...]_` placeholders where an image should
> be inserted.

> Every DocPerm row apex ships, System Manager included, is listed once in the
> [permissions reference](reference/permissions.md). It is generated from the
> shipped DocType JSON, so the per-area pages link into it rather than restating
> a matrix that can drift.
