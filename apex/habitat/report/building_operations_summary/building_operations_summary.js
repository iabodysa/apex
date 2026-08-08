// Copyright (c) 2026, afmcoltd
frappe.query_reports["Building Operations Summary"] = {
	filters: [
		apex.report_filters.building(),
		{
			fieldname: "period_from",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -7),
		},
		{
			fieldname: "period_to",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
	],
};
