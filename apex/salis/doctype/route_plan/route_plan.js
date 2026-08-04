// Copyright (c) 2026, AFMCO and contributors
frappe.ui.form.on("Route Plan", {
	refresh(frm) {
		frm.clear_custom_buttons();
		if (frm.doc.docstatus !== 1) {
			return;
		}
		if ((frm.doc.supervisor_approval || "Pending") !== "Pending") {
			return;
		}
		if (!_is_assigned_supervisor(frm)) {
			frm.dashboard.set_headline_alert(
				__("This route plan is not assigned to you."),
				"orange"
			);
			return;
		}

		frm.add_custom_button(__("Approve"), function() {
			frappe.confirm(__("Approve this route plan?"), function() {
				_record_decision(frm, "approve_route_plan", {}, __("Route plan approved."), "green");
			});
		}, __("Approval")).addClass("btn-primary");

		frm.add_custom_button(__("Reject"), function() {
			frappe.prompt(
				[
					{
						fieldname: "reason",
						fieldtype: "Small Text",
						label: __("Rejection Reason"),
						reqd: 1,
					},
				],
				function(values) {
					_record_decision(
						frm,
						"reject_route_plan",
						{ reason: values.reason },
						__("Route plan rejected."),
						"orange"
					);
				},
				__("Reject"),
				__("Reject")
			);
		}, __("Approval"));
	},
});

function _is_assigned_supervisor(frm) {
	return (
		frm.doc.route_supervisor === frappe.session.user ||
		frappe.session.user === "Administrator"
	);
}

function _record_decision(frm, method, extra_args, message, indicator) {
	frappe.call({
		method: "apex.salis.api.route_supervisor." + method,
		args: Object.assign({ name: frm.doc.name }, extra_args),
		freeze: true,
		freeze_message: __("Recording the decision..."),
		callback: function(r) {
			if (r.exc) {
				return;
			}
			frm.reload_doc();
			frappe.show_alert({ message: message, indicator: indicator });
		},
		error: function() {
			frappe.show_alert({
				message: __("Could not record the decision. Please try again."),
				indicator: "red",
			});
		},
	});
}
