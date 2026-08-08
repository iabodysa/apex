// Copyright (c) 2026, afmcoltd
frappe.query_reports["Employees Holding Multiple SIMs"] = {
	filters: [
		apex.report_filters.company(),
	],
};
