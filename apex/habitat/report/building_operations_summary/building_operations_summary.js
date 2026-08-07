// Copyright (c) 2026, AFMCO and contributors
frappe.query_reports["Building Operations Summary"] = {
	filters: [
		{
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Building",
		},
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
