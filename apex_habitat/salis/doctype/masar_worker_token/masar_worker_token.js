// Masar Worker Token — desk actions to issue / rotate a worker's personal
// Masar link and show the shareable URL + QR for printing.
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
		method: "apex_habitat.salis.doctype.masar_worker_token.masar_worker_token.issue_worker_link",
		args: { employee: frm.doc.employee, regenerate: regenerate },
		freeze: true,
		freeze_message: __("Issuing worker link…"),
		callback: (r) => {
			if (!r.message) {
				return;
			}
			frm.reload_doc();
			const m = r.message;
			const qr = m.qr
				? `<div style="text-align:center;margin:12px 0">
				     <img src="${m.qr}" alt="QR" style="width:200px;height:200px" />
				   </div>`
				: `<p style="color:#888">${__("QR rendering is unavailable on this site; share the link below.")}</p>`;
			const safe_link = frappe.utils.escape_html(m.link);
			frappe.msgprint({
				title: __("Masar Worker Link"),
				indicator: "green",
				message: `
					<div>
						<p><b>${frappe.utils.escape_html(m.employee_name || m.employee)}</b></p>
						${qr}
						<p style="word-break:break-all">
							<a href="${safe_link}" target="_blank" rel="noopener">${safe_link}</a>
						</p>
						<p style="color:#888;font-size:11px">
							${__("Anyone holding this link can view this worker's Masar app. Regenerate to revoke.")}
						</p>
					</div>`,
			});
		},
	});
}
