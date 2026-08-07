// Copyright (c) 2026, afmcoltd

frappe.query_reports["Room Bed Transfer Register"] = {
	filters: [
		{
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Building",
		},
		{
			fieldname: "party_type",
			label: __("Resident Type"),
			fieldtype: "Select",
			options: ["", "Employee", "Temporary Worker"].join("\n"),
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
	],
};
