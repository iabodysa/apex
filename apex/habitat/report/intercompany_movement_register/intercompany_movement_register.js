// Copyright (c) 2026, afmcoltd
frappe.query_reports["Intercompany Movement Register"] = {
	filters: [
		{
			fieldname: "from_company",
			label: __("From Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "to_company",
			label: __("To Company"),
			fieldtype: "Link",
			options: "Company",
		},
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
		{
			fieldname: "accounting_acknowledged",
			label: __("Accounting Acknowledged"),
			fieldtype: "Select",
			options: ["", "Yes", "No"].join("\n"),
		},
	],
};
