// Copyright (c) 2026, afmcoltd
frappe.query_reports["Housing Cleaning Audit"] = {
	filters: [
		apex.report_filters.building(),
		apex.report_filters.from_date({
			default: frappe.datetime.get_today(),
		}),
		apex.report_filters.to_date({
			default: frappe.datetime.get_today(),
		}),
	],
};
