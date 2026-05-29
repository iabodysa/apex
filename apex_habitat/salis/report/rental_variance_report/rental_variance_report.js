// Copyright (c) 2026, AFMCO and contributors
frappe.query_reports["Rental Variance Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Data",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Data",
			description: __("YYYY-MM, e.g. 2026-05"),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Data",
			description: __("YYYY-MM, e.g. 2026-05"),
		},
	],
};
