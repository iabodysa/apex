// Client-side script for Fuel Request
const FUEL_HIGH_LITRES_THRESHOLD = 200;

frappe.ui.form.on("Fuel Request", {
	refresh(frm) {
		_update_fuel_indicator(frm);

		if (frm.doc.status === "Pending") {
			frm.add_custom_button(__("Open Fuel Approval Console"), function() {
				frappe.set_route("fuel-approval-console");
			});
		}

		_check_high_volume(frm);
	},
	status(frm) {
		_update_fuel_indicator(frm);
	},
	requested_litres(frm) {
		_check_high_volume(frm);
	},
});

function _update_fuel_indicator(frm) {
	frm.page.clear_indicator();
	const colors = {
		"Pending": "orange",
		"Approved": "blue",
		"Done": "green",
		"Failed": "red",
		"Cancelled": "red",
	};
	if (frm.doc.status) {
		frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "blue");
	}
}

function _check_high_volume(frm) {
	if (
		frm.doc.requested_litres &&
		frm.doc.requested_litres > FUEL_HIGH_LITRES_THRESHOLD
	) {
		frm.dashboard.add_comment(
			__("Requested volume ({0} L) exceeds the typical threshold of {1} L. Please verify before approving.", [
				frm.doc.requested_litres,
				FUEL_HIGH_LITRES_THRESHOLD,
			]),
			"orange",
			true
		);
	}
}

frappe.listview_settings["Fuel Request"] = {
	get_indicator(doc) {
		const colors = {
			"Pending": "orange",
			"Approved": "blue",
			"Done": "green",
			"Failed": "red",
			"Cancelled": "red",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
