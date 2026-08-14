// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Salis Driver", {
	refresh(frm) {
		frm.clear_custom_buttons();
		_update_driver_indicator(frm);

		if (!frm.is_new() && frm.doc.current_vehicle) {
			frm.add_custom_button(__("Open Current Vehicle"), function() {
				frappe.set_route("Form", "Salis Vehicle", frm.doc.current_vehicle);
			});
		}

		_check_license_expiry(frm);
		_portal_link_actions(frm);
	},
	status(frm) {
		_update_driver_indicator(frm);
	},
	license_expiry(frm) {
		_check_license_expiry(frm);
	},
});

function _portal_link_actions(frm) {
	if (frm.is_new() || !frappe.model.can_write("Masar Worker Token")) {
		return;
	}
	const group = __("Driver Portal");

	if (frm.doc.status === "Active") {
		frm.add_custom_button(__("Show Portal Link"), () => _issue_portal_link(frm, 0), group);
		frm.add_custom_button(
			__("Rotate Portal Link"),
			() => {
				frappe.confirm(
					__(
						"Rotating issues a NEW barcode and stops the previous one working. Continue?"
					),
					() => _issue_portal_link(frm, 1)
				);
			},
			group
		);
	}

	frm.add_custom_button(
		__("Revoke Portal Link"),
		() => {
			frappe.confirm(
				__(
					"Revoking stops this driver's barcode working immediately. Issue a new one to restore access. Continue?"
				),
				() => _revoke_portal_link(frm)
			);
		},
		group
	);
}

function _issue_portal_link(frm, regenerate) {
	frappe.call({
		method: "apex.apex_core.doctype.masar_worker_token.masar_worker_token.issue_driver_link",
		args: { driver: frm.doc.name, regenerate: regenerate },
		freeze: true,
		freeze_message: __("Issuing driver link…"),
		callback: (r) => {
			if (r.exc || !r.message) {
				return;
			}
			apex.masar.show_driver_link_dialog(r.message);
		},
		error: () => {
			frappe.show_alert({
				message: __("Could not issue the driver link. Please try again."),
				indicator: "red",
			});
		},
	});
}

function _revoke_portal_link(frm) {
	frappe.call({
		method: "apex.apex_core.doctype.masar_worker_token.masar_worker_token.revoke_driver_link",
		args: { driver: frm.doc.name },
		freeze: true,
		freeze_message: __("Revoking driver link…"),
		callback: (r) => {
			if (r.exc || !r.message) {
				return;
			}
			frappe.show_alert({
				message: r.message.revoked
					? __("Driver link revoked.")
					: __("This driver had no live link."),
				indicator: r.message.revoked ? "green" : "orange",
			});
		},
		error: () => {
			frappe.show_alert({
				message: __("Could not revoke the driver link. Please try again."),
				indicator: "red",
			});
		},
	});
}

function _update_driver_indicator(frm) {
	frm.page.clear_indicator();
	const colors = {
		"Active": "green",
		"Stopped": "red",
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
