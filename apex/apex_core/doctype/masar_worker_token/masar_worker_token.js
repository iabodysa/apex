// Copyright (c) 2026, AFMCO and contributors
// [#o4a9j5]
frappe.ui.form.on("Masar Worker Token", {
	refresh(frm) {
		frm.clear_custom_buttons();
		if (frm.is_new()) {
			return;
		}

		// [#tokhash] The raw token is stored only as a hash, so it can never be
		// re-displayed from the record. Issuing is ROTATE-ONLY: a fresh link + QR is
		// minted and shown ONCE here; re-opening this action rotates (invalidating any
		// previously shared link) rather than re-showing the old secret.
		const has_link = Boolean(frm.doc.token);
		frm.add_custom_button(
			has_link ? __("Rotate Link and QR") : __("Issue Link and QR"),
			() => {
				if (!has_link) {
					_show_link(frm, 1);
					return;
				}
				frappe.confirm(
					__(
						"The current link cannot be shown again. Rotating issues a NEW link and QR and invalidates the previous one. Continue?"
					),
					() => _show_link(frm, 1)
				);
			}
		);

		if (!frm.doc.enabled) {
			frm.dashboard.set_headline_alert(
				__("This worker token is disabled — the personal link will not resolve."),
				"orange"
			);
		}
	},
});

// [#a267hb] A Driver row carries no employee, so the worker endpoint would have been
// called with an undefined subject; route on holder_type instead of assuming Worker.
function _show_link(frm, regenerate) {
	const is_driver = frm.doc.holder_type === "Driver";
	frappe.call({
		method: is_driver
			? "apex.apex_core.doctype.masar_worker_token.masar_worker_token.issue_driver_link"
			: "apex.apex_core.doctype.masar_worker_token.masar_worker_token.issue_worker_link",
		args: is_driver
			? { driver: frm.doc.driver, regenerate: regenerate }
			: { employee: frm.doc.employee, regenerate: regenerate },
		freeze: true,
		freeze_message: is_driver
			? __("Issuing driver link…")
			: __("Issuing worker link…"),
		callback: (r) => {
			if (r.exc || !r.message) {
				return;
			}
			frm.reload_doc();
			// [#f43ja4]
			if (is_driver) {
				apex.masar.show_driver_link_dialog(r.message);
			} else {
				apex.masar.show_worker_link_dialog(r.message);
			}
		},
		error: () => {
			frappe.show_alert({
				message: is_driver
					? __("Could not issue the driver link. Please try again.")
					: __("Could not issue the worker link. Please try again."),
				indicator: "red",
			});
		},
	});
}
