// Copyright (c) 2026, afmcoltd
frappe.query_reports["Manpower Roster and Cost"] = {
	filters: [
		apex.report_filters.field("worker_type", __("Worker Type"), "Select", {
			options: [
				{ value: "", label: __("All") },
				{ value: "Freelancer", label: __("Freelancer") },
				{ value: "Temporary Worker", label: __("Temporary Worker") },
			],
		}),
		apex.report_filters.field("status", __("Status"), "Select", {
			options: [
				{ value: "", label: __("All") },
				{ value: "Active", label: __("Active") },
				{ value: "Linked", label: __("Linked") },
				{ value: "Expired", label: __("Expired") },
				{ value: "Terminated", label: __("Terminated") },
			],
		}),
		apex.report_filters.project(),
		apex.report_filters.field("within_days", __("Ending Within (Days)"), "Int", {
			default: 60,
			description: __("Leave at zero to list every worker."),
		}),
	],
};
