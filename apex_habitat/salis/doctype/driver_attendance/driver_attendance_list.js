frappe.listview_settings["Driver Attendance"] = {
	get_indicator(doc) {
		const colors = {
			"Present": "green",
			"Absent": "red",
			"Late": "orange",
			"On Leave": "blue",
		};
		return [__(doc.status), colors[doc.status] || "grey", "status,=," + doc.status];
	},
};
