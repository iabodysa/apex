// Copyright (c) 2026, AFMCO and contributors
frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Top Workers by Custody Value"] = {
	method: "apex_habitat.habitat.dashboard_chart_source.top_workers_by_custody_value.top_workers_by_custody_value.get",
	filters: [],
};
