frappe.views.calendar["Building License"] = {
	field_map: {
		start: "expiry_date",
		end: "expiry_date",
		id: "name",
		title: "license_number",
		status: "status",
		allDay: "allDay",
	},
	status_color: {
		Active: "green",
		"Expiring Soon": "orange",
		Expired: "red",
		"Under Renewal": "blue",
		Revoked: "darkgrey",
	},
	get_events_method: "frappe.desk.calendar.get_events",
};
