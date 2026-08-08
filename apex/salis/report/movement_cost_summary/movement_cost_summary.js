// Copyright (c) 2026, afmcoltd
frappe.query_reports["Movement Cost Summary"] = {
	filters: [
		apex.report_filters.company(),
		apex.report_filters.cost_center(),
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Open", "Acknowledged", "Approved", "Recovered", "Waived", "Rejected"].join("\n"),
		},
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
	],
};
