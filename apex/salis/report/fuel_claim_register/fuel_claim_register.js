// Copyright (c) 2026, AFMCO and contributors
frappe.query_reports["Fuel Claim Register"] = {
	filters: [
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "vehicle",
			label: __("Vehicle"),
			fieldtype: "Link",
			options: "Salis Vehicle",
		},
		{
			fieldname: "period_month",
			label: __("Period (Month)"),
			fieldtype: "Data",
			description: __("YYYY-MM, e.g. 2026-05"),
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Draft", "Submitted to Movement", "Reconciled", "Approved", "Disputed", "Closed"].join("\n"),
		},
	],
};
