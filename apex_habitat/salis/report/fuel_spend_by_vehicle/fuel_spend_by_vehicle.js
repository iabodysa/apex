// Copyright (c) 2026, AFMCO and contributors
frappe.query_reports["Fuel Spend by Vehicle"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "vehicle",
			label: __("Vehicle"),
			fieldtype: "Link",
			options: "Salis Vehicle",
		},
		{
			fieldname: "period_month",
			label: __("Period (Month)"),
			fieldtype: "Data",
			description: __("YYYY-MM, e.g. 2026-05"),
		},
	],
};
