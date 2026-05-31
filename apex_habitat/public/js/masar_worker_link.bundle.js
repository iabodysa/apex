// Shared Masar worker-link desk helpers.
//
// Single source of truth for the "Masar Worker Link" result dialog (worker name,
// inline QR data-URI, shareable link, wa.me WhatsApp share, optional copy-link)
// and the phone-normalisation rule behind the WhatsApp deep link.
//
// Previously these helpers were copy-pasted into three desk JS files (the Masar
// Worker Token form, the Accommodation Assignment form, and the Arrivals Desk
// page). They now live here and are loaded on every desk page via hooks.py
// `app_include_js`. This is a `*.bundle.js` file: Frappe's esbuild builds it and
// serves it under its bare filename ("masar_worker_link.bundle.js"); a `bench
// build` is required after wiring it into hooks.py.
//
// Public surface (under the `apex_habitat.masar` namespace):
//   apex_habitat.masar.normalise_phone(raw)
//   apex_habitat.masar.show_worker_link_dialog(m, opts)

frappe.provide("apex_habitat.masar");

// Normalise a raw phone string to E.164 *digits* (no "+") suitable for wa.me,
// or return null if it can't confidently be normalised to >= 11 digits.
// Saudi-first rules: strip spaces/dashes/parens and a leading "+"; a leading
// "0" (local trunk prefix) becomes the country code "966"; a bare 9-digit
// mobile starting with "5" gets the "966" prefix.
apex_habitat.masar.normalise_phone = function (raw) {
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
};

// Render the standard "Masar Worker Link" result dialog: worker name, QR (inline
// data-URI img), the shareable link, and (when the phone normalises) a WhatsApp
// share button. Pass opts.copy_link = true to also show a "Copy link" button.
//
// @param {Object} m     Result from issue_worker_link: {employee, employee_name,
//                       link, qr, phone}.
// @param {Object} [opts] {copy_link: boolean} — show a copy-link button.
apex_habitat.masar.show_worker_link_dialog = function (m, opts) {
	opts = opts || {};
	const qr = m.qr
		? `<div style="text-align:center;margin:12px 0">
		     <img src="${m.qr}" alt="QR" style="width:200px;height:200px" />
		   </div>`
		: `<p style="color:#888">${__("QR rendering is unavailable on this site; share the link below.")}</p>`;
	const safe_link = frappe.utils.escape_html(m.link);

	const copy_button = opts.copy_link
		? `<p>
			<button class="btn btn-default btn-xs masar-copy-link">${__("Copy link")}</button>
		</p>`
		: "";

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
			${copy_button}
			<p style="color:#888;font-size:11px">
				${__("Anyone holding this link can view this worker's Masar app. Regenerate to revoke.")}
			</p>
		</div>`);

	if (opts.copy_link) {
		d.$body.find(".masar-copy-link").on("click", () => {
			frappe.utils.copy_to_clipboard(m.link);
			frappe.show_alert({ message: __("Link copied."), indicator: "green" });
		});
	}

	// Browser-only WhatsApp share (no API integration): open a wa.me deep link
	// with the personal link prefilled. Shown only when the phone normalises.
	const phone = apex_habitat.masar.normalise_phone(m.phone);
	if (phone) {
		d.set_primary_action(__("Send via WhatsApp"), () => {
			const text = __("Here is your personal Masar link: {0}", [m.link]);
			const url = `https://wa.me/${phone}?text=${encodeURIComponent(text)}`;
			window.open(url, "_blank");
		});
	}
	d.show();
};
