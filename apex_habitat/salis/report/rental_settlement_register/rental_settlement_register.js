// Copyright (c) 2026, AFMCO and contributors
frappe.query_reports["Rental Settlement Register"] = {
	filters: [
		{
			fieldname: "rental_office",
			label: __("Rental Office"),
			fieldtype: "Link",
			options: "Rental Office",
		},
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
			fieldname: "period_month",
			label: __("Period (Month)"),
			fieldtype: "Data",
			description: __("YYYY-MM, e.g. 2026-05"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
	],
};
