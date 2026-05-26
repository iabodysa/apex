// Client-side script for Sponsorship Transfer Case
frappe.ui.form.on("Sponsorship Transfer Case", {
	refresh(frm) {
		_update_case_indicator(frm);
		_warn_completion_blocked(frm);
	},
	status(frm) {
		_update_case_indicator(frm);
		_warn_completion_blocked(frm);
	},
	qiwa_status(frm) {
		_update_case_indicator(frm);
		_warn_completion_blocked(frm);
	},
	clearance_done(frm) {
		_warn_completion_blocked(frm);
	},
});

function _update_case_indicator(frm) {
	frm.page.clear_indicator();

	const qiwa_colors = {
		"Not Started": "grey",
		"Submitted": "orange",
		"Approved": "green",
		"Rejected": "red",
	};
	if (frm.doc.qiwa_status) {
		frm.page.set_indicator(
			__("Qiwa: {0}", [__(frm.doc.qiwa_status)]),
			qiwa_colors[frm.doc.qiwa_status] || "blue"
		);
	}
}

function _warn_completion_blocked(frm) {
	if (frm.doc.status === "Completed") {
		const blockers = [];
		if (frm.doc.qiwa_status !== "Approved") {
			blockers.push(__("Qiwa status is not Approved"));
		}
		if (!frm.doc.clearance_done) {
			blockers.push(__("Clearance is not done"));
		}
		if (blockers.length) {
			frm.dashboard.add_comment(
				__("This case is marked Completed but the following prerequisites are not met: {0}.", [
					blockers.join("; "),
				]),
				"red",
				true
			);
		}
	}
}

frappe.listview_settings["Sponsorship Transfer Case"] = {
	get_indicator(doc) {
		const colors = {
			"Open": "blue",
			"In Progress": "orange",
			"Completed": "green",
			"Cancelled": "red",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
