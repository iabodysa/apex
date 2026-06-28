// Copyright (c) 2026, AFMCO and contributors
frappe.ui.form.on("Custody Handover", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) {
			return;
		}
		const api = "apex_habitat.habitat.api.custody_handover.";

		if (frm.doc.status === "Pending Receipt") {
			frm.add_custom_button(__("Start Review"), () => {
				frm.set_value("status", "Under Review");
				frm.save();
			});
		}

		if (frm.doc.status === "Under Review") {
			frm.add_custom_button(__("Approve Handover"), () => {
				frappe.call({
					method: api + "approve_handover",
					args: { handover: frm.doc.name },
					freeze: true,
					callback: () => frm.reload_doc(),
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
						if (r.message) {
							frappe.msgprint({
								title: __("New One-Time Password"),
								message: __("Share this code with the receiving supervisor: {0}", [r.message]),
								indicator: "blue",
							});
						}
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
						});
					},
					__("Reject Handover"),
					__("Reject")
				);
			});
		}
	},
});
