// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Apex Settings", {
	refresh(frm) {
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
