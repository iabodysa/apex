// Client-side script for Dispatch Trip
frappe.ui.form.on("Dispatch Trip", {
	refresh(frm) {
		_update_trip_indicator(frm);

		if (!frm.is_new() && frm.doc.status === "Dispatched") {
			frm.add_custom_button(__("Complete Trip"), function() {
				_prompt_complete_trip(frm);
			}, __("Actions"));
		}
	},
	status(frm) {
		_update_trip_indicator(frm);
	},
});

function _update_trip_indicator(frm) {
	frm.page.clear_indicator();
	const colors = {
		"Planned": "blue",
		"Dispatched": "orange",
		"Completed": "green",
		"Cancelled": "red",
	};
	if (frm.doc.status) {
		frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "blue");
	}
}

function _prompt_complete_trip(frm) {
	frappe.prompt(
		[
			{
				fieldname: "odometer_end",
				label: __("Odometer End"),
				fieldtype: "Int",
				reqd: 1,
				default: frm.doc.odometer_start || 0,
			},
		],
		function(values) {
			if (
				frm.doc.odometer_start &&
				values.odometer_end < frm.doc.odometer_start
			) {
				frappe.msgprint({
					title: __("Invalid Odometer Reading"),
					message: __("Odometer end ({0}) cannot be less than odometer start ({1}).", [
						values.odometer_end,
						frm.doc.odometer_start,
					]),
					indicator: "red",
				});
				return;
			}
			frm.set_value("odometer_end", values.odometer_end);
			frm.set_value("status", "Completed");
			frm.save();
		},
		__("Complete Trip"),
		__("Complete")
	);
}

frappe.listview_settings["Dispatch Trip"] = {
	get_indicator(doc) {
		const colors = {
			"Planned": "blue",
			"Dispatched": "orange",
			"Completed": "green",
			"Cancelled": "red",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
