frappe.views.calendar["Accommodation Lease"] = {
	field_map: {
		start: "lease_start_date",
		end: "lease_end_date",
		id: "name",
		title: "building",
		status: "status",
		allDay: "allDay",
	},
	status_color: {
		Active: "green",
		Expired: "orange",
		Terminated: "red",
	},
	get_events_method: "frappe.desk.calendar.get_events",
};
