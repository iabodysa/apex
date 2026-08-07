// Copyright (c) 2026, AFMCO and contributors

frappe.query_reports["Safety Incident Register"] = {
	filters: [
		{
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Building",
		},
		{
			fieldname: "incident_type",
			label: __("Incident Type"),
			fieldtype: "Select",
			options: [
				"",
				"Fire",
				"Electrical",
				"Injury",
				"Structural",
				"Health and Hygiene",
				"Security",
				"Other",
			].join("\n"),
		},
		{
			fieldname: "severity",
			label: __("Severity"),
			fieldtype: "Select",
			options: ["", "Low", "Medium", "High", "Severe", "Critical"].join("\n"),
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Open", "Under Investigation", "Closed"].join("\n"),
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
