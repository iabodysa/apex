// Copyright (c) 2026, afmcoltd
frappe.provide("apex.web_form");

apex.web_form.adopt_url_token = function (fieldname) {
	const token = frappe.utils.get_url_arg("token");
	if (token) {
		frappe.web_form.set_value(fieldname, token);
	}
};

apex.web_form.show_tracking_code = function (doc, options) {
	const code = doc && doc.anonymous_tracking_code;
	if (!code) {
		return;
	}
	options = options || {};
	const id = options.id || "apex-tracking-code";
	if (document.getElementById(id)) {
		return;
	}

	const box = document.createElement("div");
	box.id = id;
	box.className = "alert alert-success mt-4";
	box.style.fontSize = "15px";

	const heading = document.createElement("strong");
	heading.textContent = options.heading || __("Request submitted successfully.");

	const codeEl = document.createElement("code");
	codeEl.style.cssText =
		"font-size:17px;letter-spacing:3px;font-weight:bold;margin-top:5px;display:inline-block;";
	codeEl.textContent = code;

	const hint = document.createElement("small");
	hint.className = "text-muted";
	hint.textContent = __("Save this code to follow up with your supervisor.");

	box.appendChild(heading);
	box.appendChild(document.createElement("br"));
	box.appendChild(document.createTextNode(__("Your tracking code:") + " "));
	box.appendChild(codeEl);
	box.appendChild(document.createElement("br"));
	box.appendChild(hint);

	const footer = document.querySelector(".web-form-footer");
	if (footer) {
		footer.parentNode.insertBefore(box, footer.nextSibling);
	} else {
		document.querySelector(".web-form-wrapper").appendChild(box);
	}
};
