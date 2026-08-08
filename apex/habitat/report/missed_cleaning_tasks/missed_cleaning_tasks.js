// Copyright (c) 2026, afmcoltd
frappe.query_reports["Missed Cleaning Tasks"] = {
	filters: [
		apex.report_filters.building(),
		{
			fieldname: "date_from",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -30),
		},
		{
			fieldname: "date_to",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
	],
};
