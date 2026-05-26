// Client-side script for Fuel Claim

frappe.ui.form.on("Fuel Claim", {
	refresh(frm) {
		_update_claim_indicator(frm);
		_flag_variance(frm);
	},
	status(frm) {
		_update_claim_indicator(frm);
	},
	claimed_litres(frm) {
		_flag_variance(frm);
	},
	is_increase(frm) {
		_flag_variance(frm);
	},
});

function _update_claim_indicator(frm) {
	frm.page.clear_indicator();
	const colors = {
		"Draft": "gray",
		"Submitted to Movement": "orange",
		"Reconciled": "blue",
		"Approved": "green",
		"Disputed": "red",
		"Closed": "darkgrey",
	};
	if (frm.doc.status) {
		frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "blue");
	}
}

function _flag_variance(frm) {
	const claimed = frm.doc.claimed_litres || 0;
	const variance = frm.doc.variance_litres || 0;
	if (frm.doc.is_increase) {
		frm.dashboard.add_comment(
			__("Quota-increase claim - requires Operations-tier approval and a Finance consult note."),
			"orange",
			true
		);
		return;
	}
	if (claimed > 0 && Math.abs(variance) > 0.1 * claimed) {
		frm.dashboard.add_comment(
			__("Variance ({0} L) exceeds 10% of the claimed volume - requires Operations-tier approval and a Finance consult note.", [
				variance,
			]),
			"orange",
			true
		);
	}
}

frappe.listview_settings["Fuel Claim"] = {
	get_indicator(doc) {
		const colors = {
			"Draft": "gray",
			"Submitted to Movement": "orange",
			"Reconciled": "blue",
			"Approved": "green",
			"Disputed": "red",
			"Closed": "darkgrey",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
