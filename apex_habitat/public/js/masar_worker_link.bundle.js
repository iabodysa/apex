// [#t52r33]

frappe.provide("apex_habitat.masar");

// [#qzid91]
apex_habitat.masar.normalise_phone = function (raw) {
	if (!raw) {
		return null;
	}
	// [#nm152f]
	let digits = String(raw).replace(/[^0-9]/g, "");
	if (!digits) {
		return null;
	}
	if (digits.startsWith("00")) {
		// [#h49qyu]
		digits = digits.slice(2);
	} else if (digits.startsWith("0")) {
		// [#1l11t8]
		digits = "966" + digits.slice(1);
	} else if (digits.length === 9 && digits.startsWith("5")) {
		// [#h5btug]
		digits = "966" + digits;
	}
	// [#dlfqwg]
	return digits.length >= 11 ? digits : null;
};

// [#2rwa52]
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

	// [#54fm8q]
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
