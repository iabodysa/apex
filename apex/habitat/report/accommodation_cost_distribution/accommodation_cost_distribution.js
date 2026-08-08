// Copyright (c) 2026, afmcoltd
frappe.query_reports["Accommodation Cost Distribution"] = {
	filters: [
		apex.report_filters.from_date({
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -30),
			reqd: 1,
		}),
		apex.report_filters.to_date({
			default: frappe.datetime.get_today(),
			reqd: 1,
		}),
		apex.report_filters.building(),
		apex.report_filters.project(),
		apex.report_filters.company(),
		apex.report_filters.cost_center(),
	],
};
