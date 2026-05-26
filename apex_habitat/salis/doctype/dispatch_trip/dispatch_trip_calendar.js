frappe.views.calendar["Dispatch Trip"] = {
	field_map: {
		start: "trip_date",
		end: "trip_date",
		id: "name",
		title: "driver",
		status: "status",
		allDay: "allDay",
	},
	status_color: {
		Planned: "blue",
		Dispatched: "orange",
		Completed: "green",
		Cancelled: "red",
	},
	get_events_method: "frappe.desk.calendar.get_events",
};
