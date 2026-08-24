// Copyright (c) 2026, afmcoltd

frappe.ui.form.on("Vehicle Incident", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.status !== "Under Review") {
			return;
		}

		frm.add_custom_button(__("Close Incident"), () => {
			frappe.prompt(
				{
					fieldname: "resolution",
					fieldtype: "Small Text",
					label: __("Resolution"),
					reqd: 1,
				},
				({ resolution }) => {
					frappe.call({
						method:
							"apex.salis.doctype.vehicle_incident.vehicle_incident.close_incident",
						args: { name: frm.doc.name, resolution },
						freeze: true,
						callback: () => frm.reload_doc(),
					});
				},
				__("Close Incident"),
				__("Close"),
			);
		});
	},
});
