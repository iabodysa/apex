// Copyright (c) 2026, AFMCO and contributors
frappe.query_reports["Boarding Scan Register"] = {
	filters: [
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
			fieldname: "result",
			label: __("Result"),
			fieldtype: "Select",
			options: ["", "Valid", "Duplicate", "Invalid Token", "Wrong Trip", "Expired"].join("\n"),
		},
	],
};
