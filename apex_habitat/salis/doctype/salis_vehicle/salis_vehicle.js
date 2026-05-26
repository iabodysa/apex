// Client-side script for Salis Vehicle
frappe.ui.form.on("Salis Vehicle", {
	refresh(frm) {
		_update_vehicle_indicator(frm);

		if (!frm.is_new() && frm.doc.current_driver) {
			frm.add_custom_button(__("Open Current Driver"), function() {
				frappe.set_route("Form", "Salis Driver", frm.doc.current_driver);
			}, __("Links"));
		}

		if (frm.doc.status === "Under Maintenance") {
			frm.dashboard.add_comment(
				__("This vehicle is under maintenance and should not be dispatched."),
				"orange",
				true
			);
		}
	},
	status(frm) {
		_update_vehicle_indicator(frm);
	},
});

function _update_vehicle_indicator(frm) {
	frm.page.clear_indicator();
	const colors = {
		"Active": "green",
		"Stopped": "red",
		"Under Maintenance": "orange",
		"Released": "grey",
	};
	if (frm.doc.status) {
		frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "blue");
	}
}

frappe.listview_settings["Salis Vehicle"] = {
	get_indicator(doc) {
		const colors = {
			"Active": "green",
			"Stopped": "red",
			"Under Maintenance": "orange",
			"Released": "grey",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
