// Copyright (c) 2026, afmcoltd
frappe.query_reports["Fuel Reconciliation"] = {
	filters: [
		apex.report_filters.vehicle(),
		apex.report_filters.period_month(),
	],
};
