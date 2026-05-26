frappe.views.calendar["Transport Request"] = {
	field_map: {
		start: "pickup_datetime",
		end: "pickup_datetime",
		id: "name",
		title: "destination",
		status: "status",
		allDay: "allDay",
	},
	status_color: {
		New: "blue",
		Validated: "blue",
		Approved: "blue",
		Scheduled: "orange",
		Fulfilled: "green",
		Rejected: "red",
		Cancelled: "red",
	},
	get_events_method: "frappe.desk.calendar.get_events",
};
