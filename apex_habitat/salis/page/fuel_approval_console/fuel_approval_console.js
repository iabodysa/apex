// Copyright (c) 2026, AFMCO and contributors
// [#80d3f2]

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
		// Desk page: no custom CSS (no bespoke <style> injection). Markup renders on
		// native Desk styling (frappe.ui + native btn / text-muted classes).
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
		// [#mqjs64]
		if (this._loading) return;
		this._loading = true;
		this._render_loading();
		frappe.call({
			method: "apex_habitat.salis.api.fuel_console.get_pending_fuel_requests",
			args: { project: this.project || null },
			// [#5q0uer]
			callback: (r) => {
				this._loading = false;
				if (r.exc) {
					this._render_error(this._error_text(r));
					return;
				}
				this._render_cards(r.message || []);
			},
			error: (r) => {
				this._loading = false;
				this._render_error(this._error_text(r));
			},
		});
	}

	_error_text(r) {
		// [#ajpm4h]
		let detail = "";
		try {
			if (r && r._server_messages) {
				detail = JSON.parse(r._server_messages)
					.map((m) => {
						try {
							return JSON.parse(m).message;
						} catch (e) {
							return m;
						}
					})
					.join(" ");
			}
		} catch (e) {
			detail = "";
		}
		if (!detail && r && Array.isArray(r.exc)) detail = r.exc.join(" ");
		return frappe.utils.strip_html(detail || "") || __("Could not load pending fuel requests.");
	}

	_render_loading() {
		this.$container.empty();
		const $grid = $('<div class="fac-grid"></div>').appendTo(this.$container);
		for (let i = 0; i < 6; i++) {
			$('<div class="fac-card fac-skeleton fac-skel-card"></div>').appendTo($grid);
		}
	}

	_render_error(detail) {
		this.$container.empty();
		const $box = $('<div class="fac-error" role="alert"></div>').appendTo(this.$container);
		$('<div class="fac-error-title"></div>')
			.text(__("Could not load the approval queue"))
			.appendTo($box);
		$('<div class="fac-error-detail"></div>').text(detail).appendTo($box);
		$('<button class="btn btn-sm btn-default"></button>')
			.text(__("Retry"))
			.on("click", () => this.refresh())
			.appendTo($box);
	}

	_render_cards(rows) {
		this.$container.empty();

		// [#6xlkub]
		const sorted = rows
			.slice()
			.sort((a, b) => (b.over_threshold ? 1 : 0) - (a.over_threshold ? 1 : 0));
		const over = sorted.filter((r) => r.over_threshold).length;

		const $summary = $('<div class="fac-summary"></div>').appendTo(this.$container);
		$('<span class="fac-summary-title"></span>')
			.text(__("Pending Fuel Requests"))
			.appendTo($summary);
		const $counts = $('<span class="fac-summary-counts"></span>').appendTo($summary);
		$counts.append(
			document.createTextNode(__("{0} awaiting approval", [sorted.length]))
		);
		if (over) {
			$counts.append(document.createTextNode("  ·  "));
			$('<span class="fac-over"></span>')
				.text(__("{0} over threshold", [over]))
				.appendTo($counts);
		}

		if (!sorted.length) {
			const $empty = $('<div class="fac-empty"></div>').appendTo(this.$container);
			$('<div class="fac-empty-icon"></div>').text("✓").appendTo($empty);
			$('<div></div>')
				.text(
					this.project
						? __("No pending fuel requests for this project.")
						: __("No pending fuel requests. The queue is clear.")
				)
				.appendTo($empty);
			return;
		}

		const $grid = $('<div class="fac-grid"></div>').appendTo(this.$container);
		sorted.forEach((row) => {
			this._render_card(row).appendTo($grid);
		});
	}

	_render_card(row) {
		const cls = row.over_threshold ? "fac-card fac-card--over" : "fac-card";
		const $card = $(`<div class="${cls}"></div>`);

		// [#9qgluq]
		const $head = $('<div class="fac-card-head"></div>').appendTo($card);
		const $identity = $('<div class="fac-card-identity"></div>').appendTo($head);
		$('<div class="fac-card-name"></div>')
			.text(row.driver_name || row.driver || "—")
			.appendTo($identity);
		$('<div class="fac-card-sub"></div>')
			.text(row.vehicle_plate || row.vehicle || "—")
			.appendTo($identity);
		if (row.over_threshold) {
			$('<span class="fac-card-flag"></span>')
				.text(__("Over Threshold"))
				.appendTo($head);
		}

		// [#bjmntt]
		const $metrics = $('<div class="fac-card-metrics"></div>').appendTo($card);
		// [#p2hugt]
		this._add_metric(
			$metrics,
			__("Litres"),
			frappe.format(row.requested_litres, { fieldtype: "Float" }, { inline: true })
		);
		this._add_metric(
			$metrics,
			__("Amount"),
			frappe.format(row.amount, { fieldtype: "Currency" }, { inline: true })
		);

		// [#omhdwu]
		const $body = $('<div class="fac-card-body"></div>').appendTo($card);
		this._add_row($body, __("Project"), row.project || "—");
		this._add_row($body, __("Platform"), row.fuel_platform || "—");
		if (row.age_days !== null && row.age_days !== undefined) {
			this._add_row($body, __("Age"), __("{0} day(s)", [row.age_days]));
		}

		const $foot = $('<div class="fac-card-foot"></div>').appendTo($card);
		$('<span class="fac-card-ref"></span>').text(row.name).appendTo($foot);

		const $actions = $('<div class="fac-card-actions"></div>').appendTo($foot);
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

	_add_metric($parent, label, value) {
		const $m = $('<div class="fac-metric"></div>').appendTo($parent);
		$('<span class="fac-metric-label"></span>').text(label).appendTo($m);
		$('<span class="fac-metric-value"></span>').text(value).appendTo($m);
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
						// [#jtyzu4]
						if (r.exc || !r.message) return;
						frappe.show_alert({
							message: __("Approved: {0}", [r.message.name]),
							indicator: "green",
						});
						this.refresh();
					},
					error: () => {
						frappe.show_alert({
							message: __("Approval failed for {0}.", [row.name]),
							indicator: "red",
						});
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
				d.disable_primary_action();
				frappe.call({
					method: "apex_habitat.salis.api.fuel_console.reject_fuel_request",
					args: { name: row.name, reason: values.reason },
					freeze: true,
					freeze_message: __("Rejecting…"),
					callback: (r) => {
						// [#s1fa9i]
						if (r.exc || !r.message) {
							d.enable_primary_action();
							return;
						}
						d.hide();
						frappe.show_alert({
							message: __("Rejected: {0}", [r.message.name]),
							indicator: "orange",
						});
						this.refresh();
					},
					error: () => {
						d.enable_primary_action();
						frappe.show_alert({
							message: __("Rejection failed for {0}.", [row.name]),
							indicator: "red",
						});
					},
				});
			},
		});
		d.show();
	}
}
