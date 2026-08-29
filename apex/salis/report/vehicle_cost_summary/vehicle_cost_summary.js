// Copyright (c) 2026, afmcoltd
frappe.query_reports["Vehicle Cost Summary"] = {
	filters: [
		apex.report_filters.from_date({
			reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		}),
		apex.report_filters.to_date({
			reqd: 1,
			default: frappe.datetime.get_today(),
		}),
		apex.report_filters.company(),
		apex.report_filters.project(),
		apex.report_filters.vehicle(),
	],
};
