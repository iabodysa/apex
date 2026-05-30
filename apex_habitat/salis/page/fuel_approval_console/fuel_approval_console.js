// Fuel Approval Console — pending fuel request review board (Salis).
//
// Standard Frappe page. No SPA / Vue / React / external libraries: built from
// frappe.ui.Page primitives + native frappe.ui.Dialog. All reads come from the
// single whitelisted reader get_pending_fuel_requests (no N+1); all writes route
// through the whitelisted approve_fuel_request / reject_fuel_request methods,
// which load the real Fuel Request doc and drive the native workflow. The server
// is the source of truth: after any write we re-fetch the queue rather than
// mutating the DOM optimistically.
//
// Rendering is DOM-safe: data is set via jQuery .text() / textContent only; no
// innerHTML with unescaped data. The board's styles are injected once as a
// stylesheet scoped under .fac-board (the page ships no separate CSS asset).

frappe.pages["fuel-approval-console"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Fuel Approval Console"),
		single_column: true,
	});

	const fac = new FuelApprovalConsole(page);
	fac.setup();
};

const FAC_STYLE_ID = "fac-board-styles";
const FAC_STYLES = `
.fac-board { padding: 4px 2px 24px; }
.fac-summary { display: flex; align-items: baseline; justify-content: space-between;
	flex-wrap: wrap; gap: 8px; margin: 4px 2px 16px; }
.fac-summary-title { font-size: 1.1rem; font-weight: 600; }
.fac-summary-counts { color: var(--text-muted); font-size: 0.85rem; }
.fac-summary-counts .fac-over { color: var(--red-600, #c0392b); font-weight: 600; }
.fac-empty { text-align: center; padding: 48px 16px; color: var(--text-muted);
	border: 1px dashed var(--border-color); border-radius: var(--border-radius-lg, 10px);
	background: var(--card-bg, var(--fg-color, #fff)); }
.fac-empty-icon { font-size: 2rem; line-height: 1; margin-bottom: 8px; opacity: 0.6; }
.fac-error { text-align: center; padding: 40px 16px; color: var(--text-muted);
	border: 1px solid var(--red-300, #f5c2c2); border-radius: var(--border-radius-lg, 10px);
	background: var(--red-50, #fdf3f3); }
.fac-error-title { color: var(--red-600, #c0392b); font-weight: 600; margin-bottom: 6px; }
.fac-error-detail { font-size: 0.85rem; margin-bottom: 14px; overflow-wrap: anywhere; }
.fac-skeleton { background: linear-gradient(90deg,
	var(--control-bg, #f0f1f3) 25%, var(--bg-color, #f8f9fa) 37%,
	var(--control-bg, #f0f1f3) 63%); background-size: 400% 100%;
	animation: fac-shimmer 1.4s ease infinite; border-radius: 6px; }
.fac-skel-card { height: 184px; }
@keyframes fac-shimmer { 0% { background-position: 100% 0; } 100% { background-position: -100% 0; } }
@media (prefers-reduced-motion: reduce) { .fac-skeleton { animation: none; } }
.fac-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.fac-card { display: flex; flex-direction: column; gap: 12px;
	background: var(--card-bg, var(--fg-color, #fff)); border: 1px solid var(--border-color);
	border-radius: var(--border-radius-lg, 10px); padding: 16px;
	box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.06)); transition: box-shadow 0.15s ease; }
.fac-card:hover { box-shadow: var(--shadow-md, 0 4px 12px rgba(0,0,0,0.1)); }
.fac-card--over { border-left: 4px solid var(--red-500, #e24c4c); }
.fac-card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.fac-card-identity { min-width: 0; }
.fac-card-name { font-weight: 600; font-size: 0.98rem; line-height: 1.25; overflow-wrap: anywhere; }
.fac-card-sub { color: var(--text-muted); font-size: 0.82rem; margin-top: 2px; }
.fac-card-flag { flex: none; font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
	letter-spacing: 0.03em; color: var(--red-600, #c0392b); background: var(--red-100, #fde8e8);
	border-radius: 999px; padding: 3px 8px; white-space: nowrap; }
.fac-card-metrics { display: flex; gap: 20px; padding: 10px 0;
	border-top: 1px solid var(--border-color); border-bottom: 1px solid var(--border-color); }
.fac-metric { display: flex; flex-direction: column; gap: 2px; }
.fac-metric-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.03em;
	color: var(--text-muted); }
.fac-metric-value { font-size: 1.05rem; font-weight: 600; }
.fac-card-body { display: flex; flex-direction: column; gap: 6px; }
.fac-field { display: flex; align-items: baseline; justify-content: space-between; gap: 12px;
	font-size: 0.85rem; }
.fac-field-label { color: var(--text-muted); flex: none; }
.fac-field-value { text-align: right; overflow-wrap: anywhere; }
.fac-card-foot { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.fac-card-ref { font-family: var(--font-stack-mono, monospace); font-size: 0.74rem;
	color: var(--text-muted); background: var(--control-bg, var(--bg-color, #f4f5f6));
	border-radius: 6px; padding: 2px 7px; }
.fac-card-actions { display: flex; gap: 8px; flex: none; }
@media (max-width: 480px) { .fac-grid { grid-template-columns: 1fr; } }
`;

class FuelApprovalConsole {
	constructor(page) {
		this.page = page;
		this.project = null;
	}

	setup() {
		this._inject_styles();
		this.$container = $('<div class="fac-board"></div>').appendTo(this.page.main);
		this._setup_controls();
		this.refresh();
	}

	_inject_styles() {
		if (document.getElementById(FAC_STYLE_ID)) return;
		const style = document.createElement("style");
		style.id = FAC_STYLE_ID;
		style.textContent = FAC_STYLES;
		document.head.appendChild(style);
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
		// Guard against overlapping fetches (rapid Refresh clicks / filter changes).
		if (this._loading) return;
		this._loading = true;
		this._render_loading();
		frappe.call({
			method: "apex_habitat.salis.api.fuel_console.get_pending_fuel_requests",
			args: { project: this.project || null },
			// No global freeze: the in-board skeleton communicates the load and
			// keeps the page interactive (the Refresh button stays usable).
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
		// Best-effort human-readable reason from a frappe.call failure.
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

		// Surface the requests needing scrutiny first: over-threshold, then newest.
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

		// Headline is the human identity (driver · plate); the FR code is demoted
		// to a small reference badge in the footer.
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

		// The two numbers that drive the decision, shown prominently.
		const $metrics = $('<div class="fac-card-metrics"></div>').appendTo($card);
		// `inline: true` keeps the formatter from wrapping its output in a
		// `<div style='text-align:right'>` (frappe.form.formatters._right). The
		// metric value is set via .text(), so any markup would render as literal
		// "<div ...>" text on the card. We want the bare formatted value.
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

		// Secondary context.
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
						// frappe.call surfaces server errors (exc) as a dialog
						// automatically; only act on a clean success.
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
						// On failure (exc) frappe shows the server message; keep
						// the dialog open so the reviewer can retry.
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
