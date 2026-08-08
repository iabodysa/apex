// Copyright (c) 2026, afmcoltd
frappe.query_reports["Utility Variance"] = {
	filters: [
		apex.report_filters.building(),
		apex.report_filters.company(),
	],
};
