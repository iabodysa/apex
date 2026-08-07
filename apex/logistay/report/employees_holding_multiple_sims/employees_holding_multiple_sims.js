// Copyright (c) 2026, afmcoltd
frappe.query_reports["Employees Holding Multiple SIMs"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
	],
};
