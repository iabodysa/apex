// Client-side script for Salis Driver
frappe.ui.form.on("Salis Driver", {
	refresh(frm) {
		_update_driver_indicator(frm);

		if (!frm.is_new() && frm.doc.current_vehicle) {
			frm.add_custom_button(__("Open Current Vehicle"), function() {
				frappe.set_route("Form", "Salis Vehicle", frm.doc.current_vehicle);
			}, __("Links"));
		}

		_check_license_expiry(frm);
	},
	status(frm) {
		_update_driver_indicator(frm);
	},
	license_expiry(frm) {
		_check_license_expiry(frm);
	},
});

function _update_driver_indicator(frm) {
	frm.page.clear_indicator();
	const colors = {
		"Active": "green",
		"Stopped": "red",
		"On Leave": "orange",
		"Released": "grey",
	};
	if (frm.doc.status) {
		frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "blue");
	}
}

function _check_license_expiry(frm) {
	if (
		frm.doc.license_expiry &&
		frappe.datetime.get_diff(frm.doc.license_expiry, frappe.datetime.now_date()) < 0
	) {
		frm.dashboard.add_comment(
			__("Driver license has expired. Renew before assigning to trips."),
			"red",
			true
		);
	}
}

frappe.listview_settings["Salis Driver"] = {
	get_indicator(doc) {
		const colors = {
			"Active": "green",
			"Stopped": "red",
			"On Leave": "orange",
			"Released": "grey",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
