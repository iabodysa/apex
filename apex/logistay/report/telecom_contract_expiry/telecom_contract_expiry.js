// Copyright (c) 2026, afmcoltd
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
		apex.report_filters.company(),
	],
};
