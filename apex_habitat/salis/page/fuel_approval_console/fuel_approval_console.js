// Fuel Approval Console — pending fuel request review board (Salis).
//
// Standard Frappe page. No SPA / Vue / React / external libraries: built from
// frappe.ui.Page primitives + native frappe.ui.Dialog. All reads come from the
// single whitelisted reader get_pending_fuel_requests (no N+1); all writes route
// through the whitelisted approve_fuel_request / reject_fuel_request methods,
// which load the real Fuel Request doc and save through the controller. The
// server is the source of truth: after any write we re-fetch the queue rather
// than mutating the DOM optimistically.
//
// Rendering is DOM-safe: data is set via jQuery .text() / textContent only.
// No innerHTML with unescaped data.

frappe.pages["fuel-approval-console"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Fuel Approval Console"),
		single_column: true,
	});

	const fac = new FuelApprovalConsole(page);
	fac.setup();
};

class FuelApprovalConsole {
	constructor(page) {
		this.page = page;
		this.project = null;
	}

	setup() {
		this.$container = $('<div class="fac-board"></div>').appendTo(this.page.main);
		this._setup_controls();
		this.refresh();
	}

	_setup_controls() {
		this.project_field = this.page.add_field({
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
			change: () => {
				this.project = this.project_field.get_value() || null;
				this.refresh();
			},
		});

		this.page.set_primary_action(
			__("Refresh"),
			() => this.refresh(),
			"refresh"
		);
	}

	refresh() {
		frappe.call({
			method: "apex_habitat.salis.api.fuel_console.get_pending_fuel_requests",
			args: { project: this.project || null },
			freeze: true,
			freeze_message: __("Loading pending fuel requests…"),
			callback: (r) => {
				if (r.exc) return;
				this._render_cards(r.message || []);
			},
		});
	}

	_render_empty(message) {
		this.$container.empty();
		$('<div class="fac-empty text-muted"></div>')
			.text(message)
			.appendTo(this.$container);
	}

	_render_cards(rows) {
		this.$container.empty();

		const $summary = $('<div class="fac-summary"></div>').appendTo(this.$container);
		$('<span class="fac-summary-title"></span>')
			.text(__("Pending Fuel Requests"))
			.appendTo($summary);
		$('<span class="fac-summary-counts"></span>')
			.text(__("{0} awaiting approval", [rows.length]))
			.appendTo($summary);

		if (!rows.length) {
			$('<div class="fac-empty text-muted"></div>')
				.text(__("No pending fuel requests."))
				.appendTo(this.$container);
			return;
		}

		const $grid = $('<div class="fac-grid"></div>').appendTo(this.$container);
		rows.forEach((row) => {
			this._render_card(row).appendTo($grid);
		});
	}

	_render_card(row) {
		const cls = row.over_threshold ? "fac-card fac-card--over" : "fac-card";
		const $card = $(`<div class="${cls}"></div>`);

		const $head = $('<div class="fac-card-head"></div>').appendTo($card);
		$('<span class="fac-card-name"></span>').text(row.name).appendTo($head);
		if (row.over_threshold) {
			$('<span class="fac-card-flag"></span>')
				.text(__("Over Threshold"))
				.appendTo($head);
		}

		const $body = $('<div class="fac-card-body"></div>').appendTo($card);
		this._add_row($body, __("Vehicle"), row.vehicle_plate || row.vehicle || "—");
		this._add_row($body, __("Driver"), row.driver_name || row.driver || "—");
		this._add_row(
			$body,
			__("Litres"),
			frappe.format(row.requested_litres, { fieldtype: "Float" })
		);
		this._add_row(
			$body,
			__("Amount"),
			frappe.format(row.amount, { fieldtype: "Currency" })
		);
		this._add_row($body, __("Project"), row.project || "—");
		this._add_row($body, __("Platform"), row.fuel_platform || "—");
		if (row.age_days !== null && row.age_days !== undefined) {
			this._add_row($body, __("Age"), __("{0} day(s)", [row.age_days]));
		}

		const $actions = $('<div class="fac-card-actions"></div>').appendTo($card);
		$('<button class="btn btn-sm btn-success"></button>')
			.text(__("Approve"))
			.on("click", () => this._approve(row))
			.appendTo($actions);
		$('<button class="btn btn-sm btn-danger"></button>')
			.text(__("Reject"))
			.on("click", () => this._reject(row))
			.appendTo($actions);

		return $card;
	}

	_add_row($body, label, value) {
		const $r = $('<div class="fac-field"></div>').appendTo($body);
		$('<span class="fac-field-label"></span>').text(label).appendTo($r);
		$('<span class="fac-field-value"></span>').text(value).appendTo($r);
	}

	_approve(row) {
		frappe.confirm(
			__("Approve fuel request {0}?", [row.name]),
			() => {
				frappe.call({
					method: "apex_habitat.salis.api.fuel_console.approve_fuel_request",
					args: { name: row.name },
					freeze: true,
					freeze_message: __("Approving…"),
					callback: (r) => {
						if (r.exc || !r.message) return;
						frappe.show_alert({
							message: __("Approved: {0}", [r.message.name]),
							indicator: "green",
						});
						this.refresh();
					},
				});
			}
		);
	}

	_reject(row) {
		const d = new frappe.ui.Dialog({
			title: __("Reject Fuel Request"),
			fields: [
				{
					fieldname: "context",
					fieldtype: "HTML",
					options: `<div class="text-muted" style="margin-bottom:8px">${frappe.utils.escape_html(
						row.name
					)}</div>`,
				},
				{
					fieldname: "reason",
					label: __("Reason"),
					fieldtype: "Small Text",
					reqd: 1,
				},
			],
			primary_action_label: __("Reject"),
			primary_action: (values) => {
				frappe.call({
					method: "apex_habitat.salis.api.fuel_console.reject_fuel_request",
					args: { name: row.name, reason: values.reason },
					freeze: true,
					freeze_message: __("Rejecting…"),
					callback: (r) => {
						if (r.exc || !r.message) return;
						d.hide();
						frappe.show_alert({
							message: __("Rejected: {0}", [r.message.name]),
							indicator: "orange",
						});
						this.refresh();
					},
				});
			},
		});
		d.show();
	}
}
