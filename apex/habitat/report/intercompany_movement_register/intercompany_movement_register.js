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
		{
			fieldname: "accounting_acknowledged",
			label: __("Accounting Acknowledged"),
			fieldtype: "Select",
			options: ["", "Yes", "No"].join("\n"),
		},
	],
};
