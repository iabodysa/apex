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

// Board look restored on native Desk CSS variables — no stylesheet and no injected
// <style> (the removed fac-board-styles block). Colours are Desk colour-scale vars
// (theme + dark-mode aware); spacing uses logical properties so the queue mirrors
// correctly under RTL. Applied as inline style="" overlays since a Desk page ships
// no CSS of its own.
const FAC_STYLE = {
	board: "padding-block:4px 24px;padding-inline:2px;",
	grid: "display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;",
	skel: "min-block-size:184px;border-radius:var(--border-radius-lg);background:var(--skeleton-bg);",
	summary:
		"display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-block:4px 16px;margin-inline:2px;",
	summary_title: "font-size:1.1rem;font-weight:600;",
	summary_counts: "color:var(--text-muted);font-size:0.85rem;",
	over: "color:var(--red-600);font-weight:600;",
	empty:
		"text-align:center;padding-block:48px;padding-inline:16px;color:var(--text-muted);border:1px dashed var(--border-color);border-radius:var(--border-radius-lg);background:var(--card-bg);",
	empty_icon: "font-size:2rem;line-height:1;margin-block-end:8px;opacity:0.6;",
	error:
		"text-align:center;padding-block:40px;padding-inline:16px;color:var(--text-muted);border:1px solid var(--red-300);border-radius:var(--border-radius-lg);background:var(--red-50);",
	error_title: "color:var(--red-600);font-weight:600;margin-block-end:6px;",
	error_detail: "font-size:0.85rem;margin-block-end:14px;overflow-wrap:anywhere;",
	card:
		"display:flex;flex-direction:column;gap:12px;background:var(--card-bg);border:1px solid var(--border-color);border-radius:var(--border-radius-lg);padding:16px;box-shadow:var(--shadow-sm);",
	// Over-threshold accent: a coloured start-edge bar (logical, mirrors under RTL).
	card_over: "border-inline-start:4px solid var(--red-500);",
	card_head: "display:flex;align-items:flex-start;justify-content:space-between;gap:8px;",
	card_identity: "min-inline-size:0;",
	card_name: "font-weight:600;font-size:0.98rem;line-height:1.25;overflow-wrap:anywhere;",
	card_sub: "color:var(--text-muted);font-size:0.82rem;margin-block-start:2px;",
	card_flag:
		"flex:none;font-size:0.7rem;font-weight:600;color:var(--red-600);background:var(--red-100);border-radius:999px;padding-block:3px;padding-inline:8px;white-space:nowrap;",
	metrics:
		"display:flex;gap:20px;padding-block:10px;border-block-start:1px solid var(--border-color);border-block-end:1px solid var(--border-color);",
	metric: "display:flex;flex-direction:column;gap:2px;",
	metric_label: "font-size:0.72rem;color:var(--text-muted);",
	metric_value: "font-size:1.05rem;font-weight:600;",
	body: "display:flex;flex-direction:column;gap:6px;",
	field: "display:flex;align-items:baseline;justify-content:space-between;gap:12px;font-size:0.85rem;",
	field_label: "color:var(--text-muted);flex:none;",
	field_value: "text-align:end;overflow-wrap:anywhere;",
	foot: "display:flex;align-items:center;justify-content:space-between;gap:8px;",
	ref:
		"font-family:var(--font-stack-mono);font-size:0.74rem;color:var(--text-muted);background:var(--control-bg);border-radius:6px;padding-block:2px;padding-inline:7px;",
	actions: "display:flex;gap:8px;flex:none;",
};
// Uppercasing + letter-spacing distort Arabic letter-joining → apply that eyebrow
// accent (flag chip + metric labels) only in LTR.
function fac_upper() {
	return frappe.utils.is_rtl() ? "" : "text-transform:uppercase;letter-spacing:0.03em;";
}

class FuelApprovalConsole {
	constructor(page) {
		this.page = page;
		this.project = null;
	}

	setup() {
		// Desk page: no stylesheet. The board look is restored through the inline
		// FAC_STYLE constants (native Desk CSS vars) — never a <style> injection.
		this.$container = $('<div class="fac-board"></div>')
			.attr("style", FAC_STYLE.board)
			.appendTo(this.page.main);
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
			method: "apex.salis.api.fuel_console.get_pending_fuel_requests",
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
		return strip_html(detail || "") || __("Could not load pending fuel requests.");
	}

	_render_loading() {
		this.$container.empty();
		const $grid = $('<div class="fac-grid"></div>').attr("style", FAC_STYLE.grid).appendTo(this.$container);
		for (let i = 0; i < 6; i++) {
			// Flat placeholder tile on the native --skeleton-bg Desk var (theme + dark
			// aware); the removed shimmer @keyframes can't be reproduced without a sheet.
			$('<div class="fac-card fac-skeleton fac-skel-card"></div>').attr("style", FAC_STYLE.skel).appendTo($grid);
		}
	}

	_render_error(detail) {
		this.$container.empty();
		const $box = $('<div class="fac-error" role="alert"></div>')
			.attr("style", FAC_STYLE.error)
			.appendTo(this.$container);
		$('<div class="fac-error-title"></div>')
			.attr("style", FAC_STYLE.error_title)
			.text(__("Could not load the approval queue"))
			.appendTo($box);
		$('<div class="fac-error-detail"></div>').attr("style", FAC_STYLE.error_detail).text(detail).appendTo($box);
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

		const $summary = $('<div class="fac-summary"></div>').attr("style", FAC_STYLE.summary).appendTo(this.$container);
		$('<span class="fac-summary-title"></span>')
			.attr("style", FAC_STYLE.summary_title)
			.text(__("Pending Fuel Requests"))
			.appendTo($summary);
		const $counts = $('<span class="fac-summary-counts"></span>').attr("style", FAC_STYLE.summary_counts).appendTo($summary);
		$counts.append(
			document.createTextNode(__("{0} awaiting approval", [sorted.length]))
		);
		if (over) {
			$counts.append(document.createTextNode("  ·  "));
			$('<span class="fac-over"></span>')
				.attr("style", FAC_STYLE.over)
				.text(__("{0} over threshold", [over]))
				.appendTo($counts);
		}

		if (!sorted.length) {
			const $empty = $('<div class="fac-empty"></div>').attr("style", FAC_STYLE.empty).appendTo(this.$container);
			$('<div class="fac-empty-icon"></div>').attr("style", FAC_STYLE.empty_icon).text("✓").appendTo($empty);
			$('<div></div>')
				.text(
					this.project
						? __("No pending fuel requests for this project.")
						: __("No pending fuel requests. The queue is clear.")
				)
				.appendTo($empty);
			return;
		}

		const $grid = $('<div class="fac-grid"></div>').attr("style", FAC_STYLE.grid).appendTo(this.$container);
		sorted.forEach((row) => {
			this._render_card(row).appendTo($grid);
		});
	}

	_render_card(row) {
		const cls = row.over_threshold ? "fac-card fac-card--over" : "fac-card";
		const $card = $(`<div class="${cls}"></div>`).attr(
			"style",
			FAC_STYLE.card + (row.over_threshold ? FAC_STYLE.card_over : "")
		);

		// [#9qgluq]
		const $head = $('<div class="fac-card-head"></div>').attr("style", FAC_STYLE.card_head).appendTo($card);
		const $identity = $('<div class="fac-card-identity"></div>').attr("style", FAC_STYLE.card_identity).appendTo($head);
		$('<div class="fac-card-name"></div>')
			.attr("style", FAC_STYLE.card_name)
			.text(row.driver_name || row.driver || "—")
			.appendTo($identity);
		$('<div class="fac-card-sub"></div>')
			.attr("style", FAC_STYLE.card_sub)
			.text(row.vehicle_plate || row.vehicle || "—")
			.appendTo($identity);
		if (row.over_threshold) {
			$('<span class="fac-card-flag"></span>')
				.attr("style", FAC_STYLE.card_flag + fac_upper())
				.text(__("Over Threshold"))
				.appendTo($head);
		}

		// [#bjmntt]
		const $metrics = $('<div class="fac-card-metrics"></div>').attr("style", FAC_STYLE.metrics).appendTo($card);
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
		const $body = $('<div class="fac-card-body"></div>').attr("style", FAC_STYLE.body).appendTo($card);
		this._add_row($body, __("Project"), row.project || "—");
		this._add_row($body, __("Platform"), row.fuel_platform || "—");
		if (row.age_days !== null && row.age_days !== undefined) {
			this._add_row($body, __("Age"), __("{0} day(s)", [row.age_days]));
		}

		const $foot = $('<div class="fac-card-foot"></div>').attr("style", FAC_STYLE.foot).appendTo($card);
		$('<span class="fac-card-ref"></span>').attr("style", FAC_STYLE.ref).text(row.name).appendTo($foot);

		const $actions = $('<div class="fac-card-actions"></div>').attr("style", FAC_STYLE.actions).appendTo($foot);
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
		const $m = $('<div class="fac-metric"></div>').attr("style", FAC_STYLE.metric).appendTo($parent);
		$('<span class="fac-metric-label"></span>').attr("style", FAC_STYLE.metric_label + fac_upper()).text(label).appendTo($m);
		$('<span class="fac-metric-value"></span>').attr("style", FAC_STYLE.metric_value).text(value).appendTo($m);
	}

	_add_row($body, label, value) {
		const $r = $('<div class="fac-field"></div>').attr("style", FAC_STYLE.field).appendTo($body);
		$('<span class="fac-field-label"></span>').attr("style", FAC_STYLE.field_label).text(label).appendTo($r);
		$('<span class="fac-field-value"></span>').attr("style", FAC_STYLE.field_value).text(value).appendTo($r);
	}

	_approve(row) {
		frappe.confirm(
			__("Approve fuel request {0}?", [row.name]),
			() => {
				frappe.call({
					method: "apex.salis.api.fuel_console.approve_fuel_request",
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
					method: "apex.salis.api.fuel_console.reject_fuel_request",
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
