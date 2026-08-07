// Copyright (c) 2026, afmcoltd
frappe.query_reports["Audit Remediation Status"] = {
	filters: [
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: [
				"",
				"Open",
				"In Progress",
				"Evidence Submitted",
				"Verified by Client",
				"Rejected by Client",
			].join("\n"),
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
