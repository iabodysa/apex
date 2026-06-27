"""RETIRED — Salis Dashboards now ship as native is_standard=1 module JSON.

The Salis role dashboards (Fleet Manager, Fleet Supervisor, Workers Transport,
Representatives Fleet) are now shipped as standard Dashboard records under

    salis/salis_dashboard/<slug>/<slug>.json   (is_standard=1, module=Salis)

which Frappe's ``sync_dashboards()`` imports automatically on install + migrate —
exactly like ERPNext ships its module dashboards.

This seeder previously did two things that the deep audit flagged:

1. NATIVE-FIRST violation — it hand-built the Dashboard *parents* at runtime as
   is_standard=0 records. They now ship as is_standard=1 JSON.
2. DOUBLE-PROVISIONING — ``_upsert_chart`` / ``_upsert_card`` re-created Dashboard
   Charts and Number Cards that ALREADY ship as is_standard=1 JSON under
   ``salis/dashboard_chart/`` and ``salis/number_card/`` (imported by migrate),
   flipping those records from is_standard=1 to is_standard=0 on every run. That
   chart/card creation is removed entirely; the JSON is the single source of truth.

Two dashboards this seeder built are intentionally NOT shipped as JSON:
- ``Salis Finance Manager Dashboard`` — every chart/card it referenced was a
  runtime-only spec that was never shipped as JSON, so after filtering to on-disk
  is_standard=1 records it has 0 charts. Dashboard.charts is a mandatory table, so
  an empty Dashboard cannot be imported. It is dropped (and its old is_standard=0
  row, if present, is removed by the v1_x cleanup patch).

A run-once patch (``patches/v1_x/drop_legacy_is_standard0_dashboards``) deletes
the old is_standard=0 Dashboard rows on upgrading sites so migrate re-imports
them from the new JSON as is_standard=1.

Do not re-add record-building logic here: the charts, cards, and the Dashboard
parents are all is_standard JSON now, and Dashboard.validate forbids an
is_standard Dashboard from referencing a non-standard chart/card.
"""
