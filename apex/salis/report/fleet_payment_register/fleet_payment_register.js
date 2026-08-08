// Copyright (c) 2026, afmcoltd
frappe.query_reports["Fleet Payment Register"] = {
	filters: [
		apex.report_filters.company(),
		apex.report_filters.cost_center(),
		apex.report_filters.project(),
		{
			fieldname: "expense_type",
			label: __("Expense Type"),
			fieldtype: "Select",
			options: ["", "Fuel", "Rental", "Fine / Violation", "Sponsorship Fee", "Maintenance", "Other"].join("\n"),
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Draft", "Pending Finance", "Approved by Finance", "Paid", "Rejected", "Cancelled"].join("\n"),
		},
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
	],
};
