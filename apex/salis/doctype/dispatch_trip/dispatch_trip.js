// Copyright (c) 2026, AFMCO and contributors
frappe.ui.form.on("Dispatch Trip", {
	refresh(frm) {
		frm.clear_custom_buttons();
		_update_trip_indicator(frm);

		if (!frm.is_new() && frm.doc.docstatus === 0 && frm.doc.status === "Planned") {
			frm.add_custom_button(__("Assign Transport Requests"), function() {
				_prompt_assign_requests(frm);
			}).addClass("btn-primary");
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

function _prompt_assign_requests(frm) {
	frappe.prompt(
		[
			{
				fieldname: "transport_requests",
				label: __("Transport Requests"),
				fieldtype: "MultiSelectList",
				reqd: 1,
				get_data(txt) {
					return frappe.db.get_link_options("Transport Request", txt, {
						docstatus: 1,
						status: ["in", ["Approved", "Scheduled"]],
						is_assigned: 0,
					});
				},
			},
		],
		function(values) {
			const requests = values.transport_requests || [];
			if (!requests.length) {
				frappe.show_alert({
					message: __("Select at least one transport request."),
					indicator: "orange",
				});
				return;
			}
			frappe.call({
				method: "apex.salis.doctype.dispatch_trip.dispatch_trip.assign_requests_to_trip",
				args: {
					dispatch_trip: frm.doc.name,
					transport_requests: JSON.stringify(requests),
				},
				freeze: true,
				freeze_message: __("Assigning transport requests..."),
				callback: function(r) {
					if (r.exc || !r.message) {
						return;
					}
					frm.reload_doc();
					frappe.show_alert({
						message: __("{0} request(s) assigned to this trip.", [r.message.length]),
						indicator: "green",
					});
				},
				error: function() {
					frappe.show_alert({
						message: __("Could not assign the transport requests. Please try again."),
						indicator: "red",
					});
				},
			});
		},
		__("Assign Transport Requests"),
		__("Assign")
	);
}

frappe.listview_settings["Dispatch Trip"] = {
	add_fields: ["status"],
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
