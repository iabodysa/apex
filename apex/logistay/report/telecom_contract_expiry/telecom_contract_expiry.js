// Copyright (c) 2026, AFMCO and contributors
frappe.query_reports["Telecom Contract Expiry"] = {
	filters: [
		{
			fieldname: "within_days",
			label: __("Within Days"),
			fieldtype: "Int",
			default: 90,
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
	],
};
