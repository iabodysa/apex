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
	
	box.innerHTML =
		"<strong>" + __("Request submitted successfully.") + "</strong><br>" +
		__("Your tracking code:") + " " +
		"<code style=\"font-size:17px;letter-spacing:3px;font-weight:bold;margin-top:5px;display:inline-block;\">" +
		code +
		"</code><br>" +
		"<small class=\"text-muted\">" + __("Save this code to follow up with your supervisor.") + "</small>";

	var footer = document.querySelector(".web-form-footer");
	if (footer) {
		footer.parentNode.insertBefore(box, footer.nextSibling);
	} else {
		document.querySelector(".web-form-wrapper").appendChild(box);
	}
};
