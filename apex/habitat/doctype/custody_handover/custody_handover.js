// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Custody Handover", {
	setup(frm) {
		frm.set_query("to_building", () => ({
			filters: {
				...(frm.doc.from_building ? { name: ["!=", frm.doc.from_building] } : {}),
			},
		}));
	},
	refresh(frm) {
		frm.clear_custom_buttons();
		if (frm.doc.docstatus !== 1) {
			return;
		}
		const api = "apex.habitat.api.custody_handover.";

		if (frm.doc.status === "Pending Receipt") {
			frm.add_custom_button(__("Start Review"), () => {
				frm.set_value("status", "Under Review");
				if (frm.is_dirty()) {
					frm.save();
				}
			});
		}

		if (frm.doc.status === "Under Review") {
			frm.add_custom_button(__("Approve Handover"), () => {
				frappe.call({
					method: api + "approve_handover",
					args: { handover: frm.doc.name },
					freeze: true,
					callback: () => frm.reload_doc(),
					error: () => {
						frappe.show_alert({
							message: __("Could not approve the handover. Please try again."),
							indicator: "red",
						});
					},
				});
			}).addClass("btn-primary");
		}

		if (["Pending Receipt", "Under Review", "Approved"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Confirm Handover"), () => {
				frappe.prompt(
					[{ fieldname: "otp", fieldtype: "Data", label: __("One-Time Password"), reqd: 1 }],
					(values) => {
						frappe.call({
							method: api + "confirm_handover",
							args: { handover: frm.doc.name, otp: values.otp },
							freeze: true,
							callback: () => frm.reload_doc(),
							error: () => {
								frappe.show_alert({
									message: __("Could not confirm the handover. Please try again."),
									indicator: "red",
								});
							},
						});
					},
					__("Confirm Receipt"),
					__("Confirm")
				);
			}).addClass("btn-primary");

			frm.add_custom_button(__("Regenerate OTP"), () => {
				frappe.call({
					method: api + "regenerate_handover_otp",
					args: { handover: frm.doc.name },
					freeze: true,
					callback: (r) => {
						if (r.exc || !r.message) {
							return;
						}
						frappe.msgprint({
							title: __("New One-Time Password"),
							message: __("Share this code with the receiving supervisor: {0}", [r.message]),
							indicator: "blue",
						});
					},
					error: () => {
						frappe.show_alert({
							message: __("Could not regenerate the OTP. Please try again."),
							indicator: "red",
						});
					},
				});
			});

			frm.add_custom_button(__("Reject Handover"), () => {
				frappe.prompt(
					[{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 }],
					(values) => {
						frappe.call({
							method: api + "reject_handover",
							args: { handover: frm.doc.name, reason: values.reason },
							freeze: true,
							callback: () => frm.reload_doc(),
							error: () => {
								frappe.show_alert({
									message: __("Could not reject the handover. Please try again."),
									indicator: "red",
								});
							},
						});
					},
					__("Reject Handover"),
					__("Reject")
				);
			});
		}
	},
});
