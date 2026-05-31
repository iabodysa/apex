// Masar Worker Token — desk actions to issue / rotate a worker's personal
// Masar link and show the shareable URL + QR (SVG) for printing or WhatsApp.
frappe.ui.form.on("Masar Worker Token", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(__("Show Link & QR"), () => _show_link(frm, 0));
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
			// Shared helper from public/js/masar_worker_link.bundle.js
			// (wired via hooks.py app_include_js). No copy-link button on the
			// token form — the copy button is the Arrivals Desk superset.
			apex_habitat.masar.show_worker_link_dialog(r.message);
		},
	});
}
