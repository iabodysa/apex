// Copyright (c) 2026, afmcoltd
frappe.query_reports["Boarding Scan Register"] = {
	filters: [
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
		{
			fieldname: "result",
			label: __("Result"),
			fieldtype: "Select",
			options: ["", "Valid", "Duplicate", "Invalid Token", "Wrong Trip", "Expired"].join("\n"),
		},
	],
};
