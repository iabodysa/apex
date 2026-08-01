// Copyright (c) 2026, AFMCO and contributors
frappe.ui.form.on("Apex Settings", {
	refresh(frm) {
		// frappe.boot.apex_demo_data is set by the extend_bootinfo hook and tracks the
		// demo user, so the action appears only while there is demo data to remove.
		if (!frappe.boot.apex_demo_data) {
			return;
		}
		frm.add_custom_button(__("Remove Demo Data"), () => {
			frappe.confirm(
				__(
					"Remove every record the demo build created? Nothing else on this site is touched."
				),
				() => {
					frappe.call({
						method: "apex.apex_core.setup.demo.clear_demo_data",
						freeze: true,
						freeze_message: __("Removing demo data..."),
						callback: () => {
							frappe.boot.apex_demo_data = 0;
							frm.refresh();
						},
					});
				}
			);
		});
	},
});
