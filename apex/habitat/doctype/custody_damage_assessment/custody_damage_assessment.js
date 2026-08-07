// Copyright (c) 2026, afmcoltd
const DEDUCTION_STATUS_COLORS = {
	"Not Created": "gray",
	Draft: "orange",
	Submitted: "blue",
	Paid: "green",
	Cancelled: "red",
};

frappe.ui.form.on("Custody Damage Assessment", {
	setup(frm) {
		frm.set_query("custody_return", () => ({
			filters: {
				...(frm.doc.building ? { building: frm.doc.building } : {}),
			},
		}));
	},
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		frm.call("apex.habitat.doctype.custody_damage_assessment.custody_damage_assessment.get_deduction_status", {
			assessment: frm.doc.name,
		}).then((r) => {
			if (r.exc) {
				return;
			}
			const result = r.message;
			if (!result) {
				return;
			}
			const color = DEDUCTION_STATUS_COLORS[result.status] || "gray";
			frm.dashboard.add_indicator(__("Deduction: {0}", [__(result.status)]), color);
		});
	},
});
