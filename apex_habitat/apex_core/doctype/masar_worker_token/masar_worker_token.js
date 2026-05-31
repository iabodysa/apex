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
			masar_show_worker_link_dialog(r.message);
		},
	});
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared Masar worker-link helpers.
//
// These are intentionally self-contained (no app-wide JS bundle is wired in
// hooks.py): the SAME two helpers are duplicated in the Accommodation Assignment
// form so the supervisor surface shows an identical result dialog. Keep the two
// copies in sync if you change either one.
// ─────────────────────────────────────────────────────────────────────────────

// Normalise a raw phone string to E.164 *digits* (no "+") suitable for wa.me,
// or return null if it can't confidently be normalised to >= 11 digits.
// Saudi-first rules: strip spaces/dashes/parens and a leading "+"; a leading
// "0" (local trunk prefix) becomes the country code "966"; a bare 9-digit
// mobile starting with "5" gets the "966" prefix.
function masar_normalise_phone(raw) {
	if (!raw) {
		return null;
	}
	// Keep digits only; this also drops "+", spaces, dashes and parentheses.
	let digits = String(raw).replace(/[^0-9]/g, "");
	if (!digits) {
		return null;
	}
	if (digits.startsWith("00")) {
		// International "00" prefix → drop it (it's the same as a leading "+").
		digits = digits.slice(2);
	} else if (digits.startsWith("0")) {
		// Local trunk "0" → Saudi country code.
		digits = "966" + digits.slice(1);
	} else if (digits.length === 9 && digits.startsWith("5")) {
		// Bare 9-digit Saudi mobile (e.g. 5XXXXXXXX) → prefix country code.
		digits = "966" + digits;
	}
	// Anything shorter than a plausible international number is untrustworthy.
	return digits.length >= 11 ? digits : null;
}

// Render the standard "Masar Worker Link" result dialog: worker name, QR (SVG),
// the shareable link, and (when the phone normalises) a WhatsApp share button.
function masar_show_worker_link_dialog(m) {
	const qr = m.qr
		? `<div style="text-align:center;margin:12px 0">
		     <img src="${m.qr}" alt="QR" style="width:200px;height:200px" />
		   </div>`
		: `<p style="color:#888">${__("QR rendering is unavailable on this site; share the link below.")}</p>`;
	const safe_link = frappe.utils.escape_html(m.link);

	const d = new frappe.ui.Dialog({
		title: __("Masar Worker Link"),
		indicator: "green",
	});
	d.$body.html(`
		<div>
			<p><b>${frappe.utils.escape_html(m.employee_name || m.employee)}</b></p>
			${qr}
			<p style="word-break:break-all">
				<a href="${safe_link}" target="_blank" rel="noopener">${safe_link}</a>
			</p>
			<p style="color:#888;font-size:11px">
				${__("Anyone holding this link can view this worker's Masar app. Regenerate to revoke.")}
			</p>
		</div>`);

	// Browser-only WhatsApp share (no API integration): open a wa.me deep link
	// with the personal link prefilled. Shown only when the phone normalises.
	const phone = masar_normalise_phone(m.phone);
	if (phone) {
		d.set_primary_action(__("Send via WhatsApp"), () => {
			const text = __("Here is your personal Masar link: {0}", [m.link]);
			const url = `https://wa.me/${phone}?text=${encodeURIComponent(text)}`;
			window.open(url, "_blank");
		});
	}
	d.show();
}
