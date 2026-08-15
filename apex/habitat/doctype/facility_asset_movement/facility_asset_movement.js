// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Facility Asset Movement", {
	setup(frm) {
		frm.set_query("facility_asset", () => ({
			filters: {
				...(frm.doc.from_building ? { building: frm.doc.from_building } : {}),
			},
		}));
		frm.set_query("from_room", () => ({
			filters: {
				...(frm.doc.from_building ? { building: frm.doc.from_building } : {}),
			},
		}));
		frm.set_query("to_room", () => ({
			filters: {
				...(frm.doc.to_building ? { building: frm.doc.to_building } : {}),
			},
		}));
	},
	refresh(frm) {
		frm.clear_custom_buttons();
		if (frm.doc.docstatus !== 1 || !frm.doc.is_intercompany || frm.doc.accounting_acknowledged) {
			return;
		}
		frm.add_custom_button(__("Acknowledge (Accounting)"), () => {
			frappe.call({
				method:
					"apex.habitat.doctype.facility_asset_movement.facility_asset_movement." +
					"acknowledge_intercompany_movement",
				args: { movement: frm.doc.name },
				freeze: true,
				callback: () => frm.reload_doc(),
				error: () => {
					frappe.show_alert({
						message: __("Could not record the accounting acknowledgement."),
						indicator: "red",
					});
				},
			});
		}).addClass("btn-primary");
	},
});
