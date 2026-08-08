// Copyright (c) 2026, afmcoltd
frappe.query_reports["Fuel Spend by Vehicle"] = {
	filters: [
		apex.report_filters.company(),
		apex.report_filters.vehicle(),
		apex.report_filters.period_month(),
	],
};
