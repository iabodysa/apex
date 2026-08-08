// Copyright (c) 2026, afmcoltd
frappe.query_reports["Vehicle Utilisation"] = {
	filters: [
		apex.report_filters.vehicle(),
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
	],
};
