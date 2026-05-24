// Client-side script for Accommodation Building
frappe.ui.form.on("Accommodation Building", {
	refresh(frm) {
		// Status indicator
		const colors = {
			"Active": "green",
			"Inactive": "grey",
			"Under Renovation": "orange",
		};
		const status = frm.doc.status;
		if (status) {
			frm.page.set_indicator(__(status), colors[status] || "blue");
		}

		// Setup button group (only for saved documents)
		if (!frm.is_new()) {
			frm.add_custom_button(__("Quick Room Setup"), function () {
				showStep1(frm);
			}, __("Setup"));

			frm.add_custom_button(__("Generate from Table"), function () {
				frappe.confirm(
					__("Are you sure you want to generate rooms and beds from the floor plan?"),
					function () {
						frappe.call({
							method: "apex_habitat.habitat.doctype.accommodation_building.accommodation_building.generate_rooms_and_beds",
							args: { building_name: frm.doc.name },
							freeze: true,
							freeze_message: __("Generating Rooms & Beds…"),
							callback: function (r) {
								if (!r.exc) frm.reload_doc();
							}
						});
					}
				);
			}, __("Setup"));

			frm.add_custom_button(__("Generate Safety Setup"), function () {
				frappe.confirm(
					__("Are you sure you want to generate safety setup templates for this building?"),
					function () {
						frappe.call({
							method: "apex_habitat.habitat.doctype.accommodation_building.accommodation_building.generate_safety_setup",
							args: { building_name: frm.doc.name },
							freeze: true,
							freeze_message: __("Generating Safety Setup…"),
							callback: function (r) {
								if (!r.exc) frm.reload_doc();
							}
						});
					}
				);
			}, __("Setup"));
		}
	},
});

// ---------------------------------------------------------------------------
// Step 1 — Building Identity
// ---------------------------------------------------------------------------
function showStep1(frm, prefill) {
	const d1 = new frappe.ui.Dialog({
		title: __("Room Generator — Step 1 of 3: Building Code"),
		fields: [
			{
				fieldname: "abbreviation",
				fieldtype: "Data",
				label: __("Building Abbreviation"),
				reqd: 1,
				default: (prefill && prefill.abbreviation) || frm.doc.abbreviation || "",
				description: __("Short code for all room/bed IDs. Example: 'JED1' → rooms JED1-G01, JED1-101…"),
			},
			{
				fieldname: "has_ground_floor",
				fieldtype: "Check",
				label: __("Has Ground Floor (Floor 0)"),
				default: (prefill && prefill.has_ground_floor !== undefined) ? prefill.has_ground_floor : 1,
				description: __("Ground floor rooms use code G: JED1-G01, JED1-G02…"),
			},
			{
				fieldname: "num_upper_floors",
				fieldtype: "Int",
				label: __("Number of Upper Floors"),
				reqd: 1,
				default: (prefill && prefill.num_upper_floors) || 3,
				description: __("Upper floors numbered 1, 2, 3…"),
			},
		],
		primary_action_label: __("Next →"),
		primary_action(values) {
			if (!values.abbreviation || !values.abbreviation.trim()) {
				frappe.msgprint({ message: __("Building Abbreviation is required."), indicator: "red" });
				return;
			}
			d1.hide();
			showStep2(frm, values);
		},
	});
	d1.show();
}

// ---------------------------------------------------------------------------
// Step 2 — Floor Configuration
// ---------------------------------------------------------------------------
function showStep2(frm, step1Values, prefill) {
	const d2 = new frappe.ui.Dialog({
		title: __("Room Generator — Step 2 of 3: Floor Details"),
		fields: [
			{
				fieldname: "rooms_per_floor",
				fieldtype: "Int",
				label: __("Rooms per Floor"),
				reqd: 1,
				default: (prefill && prefill.rooms_per_floor) || 10,
			},
			{
				fieldname: "beds_per_room",
				fieldtype: "Int",
				label: __("Beds per Room"),
				reqd: 1,
				default: (prefill && prefill.beds_per_room) || 4,
			},
			{
				fieldname: "room_type",
				fieldtype: "Select",
				label: __("Room Type"),
				options: "Standard\nSupervisor\nIsolation\nStorage",
				default: (prefill && prefill.room_type) || "Standard",
			},
			{
				fieldname: "generate_beds",
				fieldtype: "Check",
				label: __("Auto-Generate Beds"),
				default: (prefill && prefill.generate_beds !== undefined) ? prefill.generate_beds : 1,
			},
		],
		primary_action_label: __("Next →"),
		primary_action(values) {
			d2.hide();
			showStep3(frm, step1Values, values);
		},
		secondary_action_label: __("← Back"),
		secondary_action() {
			d2.hide();
			showStep1(frm, step1Values);
		},
	});
	d2.show();
}

// ---------------------------------------------------------------------------
// Step 3 — Review & Generate
// ---------------------------------------------------------------------------
function showStep3(frm, step1Values, step2Values) {
	const abbr = step1Values.abbreviation.trim().toUpperCase();
	const hasGround = step1Values.has_ground_floor;
	const numUpper = parseInt(step1Values.num_upper_floors) || 0;
	const roomsPerFloor = parseInt(step2Values.rooms_per_floor) || 0;
	const bedsPerRoom = parseInt(step2Values.beds_per_room) || 0;
	const generateBeds = step2Values.generate_beds;

	// Build preview rows
	const floors = [];
	if (hasGround) {
		const exampleRoom = abbr + "-G01";
		floors.push({
			floorNumber: 0,
			floorCode: "G",
			rooms: roomsPerFloor,
			beds: generateBeds ? roomsPerFloor * bedsPerRoom : 0,
			example: exampleRoom,
		});
	}
	for (let i = 1; i <= numUpper; i++) {
		const exampleRoom = abbr + "-" + String(i) + "01";
		floors.push({
			floorNumber: i,
			floorCode: String(i),
			rooms: roomsPerFloor,
			beds: generateBeds ? roomsPerFloor * bedsPerRoom : 0,
			example: exampleRoom,
		});
	}

	const totalRooms = floors.reduce((s, f) => s + f.rooms, 0);
	const totalBeds = floors.reduce((s, f) => s + f.beds, 0);

	// Build HTML preview table
	let tableRows = floors.map(f => `
		<tr>
			<td>${f.floorNumber === 0 ? __("Ground") : f.floorNumber}</td>
			<td>${f.floorCode}</td>
			<td>${f.rooms}</td>
			<td>${f.beds}</td>
			<td><code>${f.example}</code></td>
		</tr>
	`).join("");

	const previewHtml = `
		<div style="margin-bottom: 12px;">
			<table class="table table-bordered table-condensed" style="font-size: 13px;">
				<thead>
					<tr style="background: #f5f5f5;">
						<th>${__("Floor")}</th>
						<th>${__("Floor Code")}</th>
						<th>${__("Rooms")}</th>
						<th>${__("Bed Count")}</th>
						<th>${__("Example Room")}</th>
					</tr>
				</thead>
				<tbody>
					${tableRows}
				</tbody>
			</table>
			<p style="margin-top: 8px; font-weight: 600;">
				${__("Total")}: ${totalRooms} ${__("rooms")}, ${totalBeds} ${__("beds")}
			</p>
		</div>
	`;

	const d3 = new frappe.ui.Dialog({
		title: __("Room Generator — Step 3 of 3: Review"),
		fields: [
			{
				fieldname: "preview",
				fieldtype: "HTML",
				options: previewHtml,
			},
		],
		primary_action_label: __("Generate Rooms & Beds ✓"),
		primary_action() {
			d3.hide();
			_applyWizard(frm, {
				abbreviation: step1Values.abbreviation.trim(),
				has_ground_floor: hasGround,
				num_upper_floors: numUpper,
				rooms_per_floor: roomsPerFloor,
				beds_per_room: bedsPerRoom,
				room_type: step2Values.room_type,
				generate_beds: generateBeds,
			});
		},
		secondary_action_label: __("← Back"),
		secondary_action() {
			d3.hide();
			showStep2(frm, step1Values, step2Values);
		},
	});
	d3.show();
}

// ---------------------------------------------------------------------------
// Apply wizard values — update floor_plan child table and trigger generation
// ---------------------------------------------------------------------------
function _applyWizard(frm, v) {
	function _buildAndSave() {
		// Clear existing floor plan rows
		frm.doc.floor_plan = [];

		// Ground floor
		if (v.has_ground_floor) {
			let row = frm.add_child("floor_plan");
			row.floor_number = 0;
			row.room_count = v.rooms_per_floor;
			row.bed_capacity_per_room = v.beds_per_room;
			row.room_type = v.room_type;
			row.generate_beds = v.generate_beds ? 1 : 0;
			row.starting_room_number = 1;
		}

		// Upper floors
		for (let i = 1; i <= v.num_upper_floors; i++) {
			let row = frm.add_child("floor_plan");
			row.floor_number = i;
			row.room_count = v.rooms_per_floor;
			row.bed_capacity_per_room = v.beds_per_room;
			row.room_type = v.room_type;
			row.generate_beds = v.generate_beds ? 1 : 0;
			row.starting_room_number = 1;
		}

		frm.refresh_field("floor_plan");

		frm.save("Update", function () {
			frappe.call({
				method: "apex_habitat.habitat.doctype.accommodation_building.accommodation_building.generate_rooms_and_beds",
				args: { building_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Generating Rooms & Beds…"),
				callback: function (r) {
					if (!r.exc) frm.reload_doc();
				}
			});
		});
	}

	// Update abbreviation on the server first if it changed
	if (v.abbreviation && v.abbreviation !== frm.doc.abbreviation) {
		frappe.db.set_value(
			"Accommodation Building",
			frm.doc.name,
			"abbreviation",
			v.abbreviation
		).then(() => {
			frm.doc.abbreviation = v.abbreviation;
			_buildAndSave();
		});
	} else {
		_buildAndSave();
	}
}
