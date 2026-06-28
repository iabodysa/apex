// Copyright (c) 2026, AFMCO and contributors
// [#3h8kmi]
const DEDUCTION_STATUS_COLORS = {
	"Not Created": "gray",
	Draft: "orange",
	Submitted: "blue",
	Paid: "green",
	Cancelled: "red",
};

frappe.ui.form.on("Custody Damage Assessment", {
	refresh(frm) {
		// [#g123bl]
		if (frm.is_new()) {
			return;
		}
		frm.call("apex_habitat.habitat.doctype.custody_damage_assessment.custody_damage_assessment.get_deduction_status", {
			assessment: frm.doc.name,
		}).then((r) => {
			const result = r.message;
			if (!result) {
				return;
			}
			const color = DEDUCTION_STATUS_COLORS[result.status] || "gray";
			frm.dashboard.add_indicator(__("Deduction: {0}", [__(result.status)]), color);
		});
	},
});
