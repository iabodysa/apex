// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Dispatch Trip", {
	refresh(frm) {
		frm.clear_custom_buttons();
		_update_trip_indicator(frm);

		if (!frm.is_new() && frm.doc.docstatus === 0 && frm.doc.status === "Planned") {
			frm.add_custom_button(__("Assign Transport Request"), function() {
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
	const stops = (frm.doc.stops || []).map((stop) => ({
		label: stop.stop_name,
		value: stop.stop_key,
	}));
	if (!stops.length) {
		frappe.msgprint(__("Add trip stops before assigning requests."));
		return;
	}
	frappe.prompt(
		[
			{
				fieldname: "transport_request",
				label: __("Transport Request"),
				fieldtype: "Link",
				options: "Transport Request",
				reqd: 1,
				get_query() {
					return {
						filters: {
							docstatus: 1,
							status: ["in", ["Approved", "Scheduled"]],
							is_assigned: 0,
						},
					};
				},
			},
			{
				fieldname: "pickup_stop",
				label: __("Pickup Stop"),
				fieldtype: "Select",
				options: stops,
				reqd: 1,
			},
			{
				fieldname: "dropoff_stop",
				label: __("Drop-off Stop"),
				fieldtype: "Select",
				options: stops,
				reqd: 1,
			},
		],
		function(values) {
			frappe.call({
				method: "apex.salis.doctype.dispatch_trip.dispatch_trip.assign_requests_to_trip",
				args: {
					dispatch_trip: frm.doc.name,
					transport_requests: JSON.stringify(values),
				},
				freeze: true,
				freeze_message: __("Assigning transport requests..."),
				callback: function(r) {
					if (r.exc || !r.message) {
						return;
					}
					frm.reload_doc();
					frappe.show_alert({
						message: __("Transport request assigned."),
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
		__("Assign Transport Request"),
		__("Assign")
	);
}
