// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Facility Asset Delivery", {
	setup(frm) {
		frm.set_query("facility_asset", () => ({
			filters: {
				...(frm.doc.from_building ? { building: frm.doc.from_building } : {}),
			},
		}));
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
		const api = "apex.habitat.api.facility_asset_delivery.";

		const call = (method, on_done) =>
			frappe.call({
				method: api + method,
				args: { delivery: frm.doc.name },
				freeze: true,
				callback: (r) => {
					if (on_done) on_done(r);
					frm.reload_doc();
				},
				error: () => {
					frappe.show_alert({
						message: __("Action failed. Please review and try again."),
						indicator: "red",
					});
				},
			});

		if (frm.doc.status === "Pending Exits") {
			if (!frm.doc.exit1_security_cleared) {
				frm.add_custom_button(__("Pass Exit 1 — Hand-over"), () =>
					call("pass_exit_1")
				).addClass("btn-primary");
			} else if (!frm.doc.exit3_receiving_cleared) {
				frm.add_custom_button(__("Pass Exit 2 — Receiving"), () =>
					call("pass_exit_3", (r) => {
						if (r.message) {
							frappe.msgprint({
								title: __("Transfer Lock Released"),
								message: __("Share the on-site code with the receiving supervisor."),
								indicator: "green",
							});
						}
					})
				).addClass("btn-primary");
			}
		}

		if (frm.doc.status === "Released") {
			frm.add_custom_button(__("Confirm Receipt"), () => {
				frappe.prompt(
					[
						{
							fieldname: "code",
							fieldtype: "Data",
							label: __("On-Site Code"),
							reqd: 1,
						},
					],
					(values) => {
						frappe.call({
							method: api + "confirm_receipt",
							args: { delivery: frm.doc.name, code: values.code },
							freeze: true,
							callback: () => frm.reload_doc(),
							error: () => {
								frappe.show_alert({
									message: __("Could not confirm receipt. Please try again."),
									indicator: "red",
								});
							},
						});
					},
					__("Confirm On-Site Receipt"),
					__("Confirm")
				);
			}).addClass("btn-primary");

			frm.add_custom_button(__("Regenerate Code"), () => {
				frappe.call({
					method: api + "regenerate_code",
					args: { delivery: frm.doc.name },
					freeze: true,
					callback: (r) => {
						if (r.exc || !r.message) {
							return;
						}
						frappe.msgprint({
							title: __("New On-Site Code"),
							message: __("Share this code with the receiving supervisor: {0}", [r.message]),
							indicator: "blue",
						});
					},
					error: () => {
						frappe.show_alert({
							message: __("Could not regenerate the code. Please try again."),
							indicator: "red",
						});
					},
				});
			});
		}
	},
});
