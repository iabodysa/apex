// Client-side script for Scheduled Task Instance
frappe.ui.form.on("Scheduled Task Instance", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status === "Open") {
			frm.add_custom_button(__("Start Task"), function () {
				frappe.confirm(
					__("Mark this Task Instance as In Progress?"),
					function () {
						frappe.call({
							method: "apex_habitat.habitat.doctype.scheduled_task_instance.scheduled_task_instance.start_task",
							args: { task_instance: frm.doc.name },
							freeze: true,
							freeze_message: __("Updating status..."),
							callback: function (r) {
								if (!r.exc) {
									frappe.show_alert({
										message: __("Task Instance marked In Progress."),
										indicator: "blue",
									});
									frm.reload_doc();
								}
							},
						});
					}
				);
			}, __("Status"));
		}
	}
});
