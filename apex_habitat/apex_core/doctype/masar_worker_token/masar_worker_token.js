// Copyright (c) 2026, AFMCO and contributors
// [#o4a9j5]
frappe.ui.form.on("Masar Worker Token", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(__("Show Link and QR"), () => _show_link(frm, 0));
		frm.add_custom_button(__("Regenerate Token"), () => {
			frappe.confirm(
				__(
					"Regenerating invalidates the worker's current link and QR. Continue?"
				),
				() => _show_link(frm, 1)
			);
		});

		if (!frm.doc.enabled) {
			frm.dashboard.set_headline_alert(
				__("This worker token is disabled — the personal link will not resolve."),
				"orange"
			);
		}
	},
});

function _show_link(frm, regenerate) {
	frappe.call({
		method: "apex_habitat.apex_core.doctype.masar_worker_token.masar_worker_token.issue_worker_link",
		args: { employee: frm.doc.employee, regenerate: regenerate },
		freeze: true,
		freeze_message: __("Issuing worker link…"),
		callback: (r) => {
			if (!r.message) {
				return;
			}
			frm.reload_doc();
			// [#f43ja4]
			apex_habitat.masar.show_worker_link_dialog(r.message);
		},
	});
}
