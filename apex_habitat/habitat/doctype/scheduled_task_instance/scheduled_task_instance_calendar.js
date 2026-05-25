frappe.views.calendar["Scheduled Task Instance"] = {
	field_map: {
		start: "due_date",
		end: "due_date",
		id: "name",
		title: "template",
		status: "status",
		allDay: "allDay",
	},
	status_color: {
		Open: "blue",
		"In Progress": "orange",
		Completed: "green",
		Overdue: "red",
		Cancelled: "darkgrey",
	},
	get_events_method: "frappe.desk.calendar.get_events",
};
