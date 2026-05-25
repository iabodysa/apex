frappe.views.calendar["Subcontractor Service Order"] = {
	field_map: {
		start: "scheduled_date",
		end: "scheduled_date",
		id: "name",
		title: "supplier",
		status: "status",
		allDay: "allDay",
	},
	status_color: {
		Scheduled: "blue",
		"In Progress": "orange",
		Completed: "green",
		Missed: "red",
		Cancelled: "darkgrey",
	},
	get_events_method: "frappe.desk.calendar.get_events",
};
