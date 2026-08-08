// Copyright (c) 2026, afmcoltd

frappe.query_reports["Safety Incident Register"] = {
	filters: [
		apex.report_filters.building(),
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
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
	],
};
