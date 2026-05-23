frappe.ready(function() {
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get("token");

    if (token) {
        frappe.web_form.set_value("location_token", token);
    }

    frappe.web_form.set_df_property("location_token", "hidden", 1);
});
