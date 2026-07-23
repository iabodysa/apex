// Copyright (c) 2026, AFMCO and contributors
frappe.query_reports["Custody Outstanding by Worker"] = {
	filters: [
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Building",
		},
		{
			fieldname: "as_on_date",
			label: __("As On Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "show_zero_balances",
			label: __("Show Zero Balances"),
			fieldtype: "Check",
		},
	],
};
