// Copyright (c) 2026, afmcoltd
frappe.query_reports["Accommodation Occupancy Summary"] = {
	filters: [
		apex.report_filters.building(),
	],
};
