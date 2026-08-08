// Copyright (c) 2026, afmcoltd
frappe.query_reports["Operational Depreciation Aging"] = {
	filters: [
		apex.report_filters.building(),
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
	],
};
