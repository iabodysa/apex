frappe.views.calendar["Driver Attendance"] = {
	field_map: {
		start: "attendance_date",
		end: "attendance_date",
		id: "name",
		title: "driver",
		status: "status",
		allDay: "allDay",
	},
	status_color: {
		Present: "green",
		Absent: "red",
		Late: "orange",
		"On Leave": "blue",
	},
	get_events_method: "frappe.desk.calendar.get_events",
};
