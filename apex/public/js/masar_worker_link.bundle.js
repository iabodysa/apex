// Copyright (c) 2026, afmcoltd

frappe.provide("apex.masar");

apex.masar.normalise_phone = function (raw) {
	if (!raw) {
		return null;
	}
	let digits = String(raw).replace(/[^0-9]/g, "");
	if (!digits) {
		return null;
	}
	if (digits.startsWith("00")) {
		digits = digits.slice(2);
	} else if (digits.startsWith("0")) {
		digits = "966" + digits.slice(1);
	} else if (digits.length === 9 && digits.startsWith("5")) {
		digits = "966" + digits;
	}
	return digits.length >= 11 ? digits : null;
};

apex.masar.show_portal_link_dialog = function (m, opts) {
	opts = opts || {};
	const qr = m.qr
		? `<div style="text-align:center;margin:12px 0">
		     <img src="${frappe.utils.escape_html(m.qr)}" alt="QR" style="width:200px;height:200px" />
		   </div>`
		: `<p style="color:#888">${__("QR rendering is unavailable on this site; share the link below.")}</p>`;
	const safe_link = frappe.utils.escape_html(m.link);

	const copy_button = opts.copy_link
		? `<p>
			<button class="btn btn-default btn-xs masar-copy-link">${__("Copy link")}</button>
		</p>`
		: "";

	const expiry = m.expires_on
		? `<p style="font-size:11px">
			${__("Expires on {0}", [frappe.datetime.str_to_user(m.expires_on)])}
		</p>`
		: "";

	const d = new frappe.ui.Dialog({
		title: opts.title || __("Masar Worker Link"),
		indicator: "green",
	});
	d.$body.html(`
		<div>
			<p><b>${frappe.utils.escape_html(opts.holder || "")}</b></p>
			${qr}
			<p style="word-break:break-all">
				<a href="${safe_link}" target="_blank" rel="noopener">${safe_link}</a>
			</p>
			${copy_button}
			${expiry}
			<p style="color:#888;font-size:11px">${opts.note || ""}</p>
		</div>`);

	if (opts.copy_link) {
		d.$body.find(".masar-copy-link").on("click", () => {
			frappe.utils.copy_to_clipboard(m.link);
			frappe.show_alert({ message: __("Link copied."), indicator: "green" });
		});
	}

	const phone = apex.masar.normalise_phone(m.phone);
	if (phone) {
		d.set_primary_action(__("Send via WhatsApp"), () => {
			const text = opts.share_text
				? opts.share_text(m.link)
				: __("Here is your personal Masar link: {0}", [m.link]);
			const url = `https://wa.me/${phone}?text=${encodeURIComponent(text)}`;
			window.open(url, "_blank");
		});
	}
	d.show();
};

apex.masar.show_worker_link_dialog = function (m, opts) {
	apex.masar.show_portal_link_dialog(m, {
		...(opts || {}),
		title: __("Masar Worker Link"),
		holder: m.employee_name || m.employee,
		note: __("Anyone holding this link can view this worker's Masar app. Regenerate to revoke."),
	});
};

apex.masar.show_driver_link_dialog = function (m, opts) {
	apex.masar.show_portal_link_dialog(m, {
		...(opts || {}),
		title: __("Driver Portal Link"),
		holder: m.driver_name || m.driver,
		note: __(
			"This barcode signs the driver in with no password. Anyone holding it enters as this driver until it expires or is revoked."
		),
		share_text: (link) => __("Here is your personal driver link: {0}", [link]),
	});
};
