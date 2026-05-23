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
	box.style.cssText = [
		"margin-top:16px",
		"padding:14px 18px",
		"background:#f0fdf4",
		"border:1px solid #86efac",
		"border-radius:6px",
		"font-size:15px",
		"line-height:1.6",
	].join(";");
	box.innerHTML =
		"<strong>Request submitted.</strong><br>" +
		"Your tracking code: " +
		"<code style=\"font-size:17px;letter-spacing:3px;font-weight:bold;\">" +
		code +
		"</code><br>" +
		"<small style=\"color:#6b7280;\">Save this code to follow up with your supervisor.</small>";

	var footer = document.querySelector(".web-form-footer");
	if (footer) {
		footer.parentNode.insertBefore(box, footer.nextSibling);
	} else {
		document.querySelector(".web-form-wrapper").appendChild(box);
	}
};
