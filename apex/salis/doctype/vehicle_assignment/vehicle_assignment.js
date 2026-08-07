// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Vehicle Assignment", {
	refresh(frm) {
		frm.clear_custom_buttons();
		_update_assignment_indicator(frm);

		if (!frm.is_new() && frm.doc.vehicle) {
			frm.add_custom_button(__("Open Vehicle"), function() {
				frappe.set_route("Form", "Salis Vehicle", frm.doc.vehicle);
			});
		}

		if (!frm.is_new() && frm.doc.driver) {
			frm.add_custom_button(__("Open Driver"), function() {
				frappe.set_route("Form", "Salis Driver", frm.doc.driver);
			});
		}

		_show_context(frm);
	},
	status(frm) {
		_update_assignment_indicator(frm);
	},
});

function _update_assignment_indicator(frm) {
	frm.page.clear_indicator();
	const colors = {
		"Active": "green",
		"Ended": "grey",
	};
	if (frm.doc.status) {
		frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "blue");
	}
}

function _show_context(frm) {
	if (frm.doc.vehicle && frm.doc.driver) {
		frm.dashboard.add_comment(
			__("Vehicle {0} is assigned to driver {1}.", [frm.doc.vehicle, frm.doc.driver]),
			"blue",
			true
		);
	}
}
