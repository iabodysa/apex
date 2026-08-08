// Copyright (c) 2026, afmcoltd
frappe.query_reports["Cost by Dimension"] = {
	filters: [
		apex.report_filters.company(),
		apex.report_filters.building(),
		apex.report_filters.project(),
		apex.report_filters.from_date({
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		}),
		apex.report_filters.to_date({
			default: frappe.datetime.get_today(),
		}),
	],
};
