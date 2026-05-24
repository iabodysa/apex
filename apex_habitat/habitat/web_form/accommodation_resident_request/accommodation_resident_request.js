frappe.web_form.after_load = function () {
	var token = new URLSearchParams(window.location.search).get("token");
	if (token) {
		frappe.web_form.set_value("location_token", token);
	}
};

frappe.web_form.after_save = function (doc) {
	var code = doc && doc.anonymous_tracking_code;
	if (!code) return;

	var existing = document.getElementById("habitat-tracking-code");
	if (existing) return;

	var box = document.createElement("div");
	box.id = "habitat-tracking-code";
	box.className = "alert alert-success mt-4";
	box.style.fontSize = "15px";

	// Fix: build DOM nodes instead of injecting via innerHTML so that the
	// server-generated tracking code cannot be interpreted as markup.
	var heading = document.createElement("strong");
	heading.textContent = __("Request submitted successfully.");

	var br1 = document.createElement("br");

	var codeLabel = document.createTextNode(__("Your tracking code:") + " ");

	var codeEl = document.createElement("code");
	codeEl.style.cssText = "font-size:17px;letter-spacing:3px;font-weight:bold;margin-top:5px;display:inline-block;";
	// Fix 4: use textContent (equivalent to frappe.utils.escape_html) so the
	// hash value is never parsed as HTML.
	codeEl.textContent = frappe.utils.escape_html(code);

	var br2 = document.createElement("br");

	var hint = document.createElement("small");
	hint.className = "text-muted";
	hint.textContent = __("Save this code to follow up with your supervisor.");

	box.appendChild(heading);
	box.appendChild(br1);
	box.appendChild(codeLabel);
	box.appendChild(codeEl);
	box.appendChild(br2);
	box.appendChild(hint);

	var footer = document.querySelector(".web-form-footer");
	if (footer) {
		footer.parentNode.insertBefore(box, footer.nextSibling);
	} else {
		document.querySelector(".web-form-wrapper").appendChild(box);
	}
};
