frappe.pages["safety-checklist"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Safety Checklist"),
		single_column: true,
	});

	const sc = new SafetyChecklist(page);
	sc.setup();
};

// Mirrors the Safety Task Execution execution_status options (Excellent wins as
// the default), kept in the same order as the DocType Select.
const SC_STATUS_OPTIONS = ["Excellent", "Good", "Average", "Poor", "Not Done"];
// Mirrors the Safety Round cadence options.
const SC_CADENCE_OPTIONS = ["Daily", "Weekly", "Monthly", "Quarterly", "Annual"];

class SafetyChecklist {
	constructor(page) {
		this.page = page;
		this.building = null;
		this.cadence = null;
		this.tasks = [];
		// task name -> { status_field, note_field } controls for one row.
		this.rows = {};
	}

	setup() {
		this.$container = $('<div class="sc-checklist"></div>').appendTo(this.page.main);
		this._render_empty(__("Pick a building and a cadence to build the checklist."));
		this._setup_controls();
	}

	_setup_controls() {
		this.building_field = this.page.add_field({
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Accommodation Building",
			change: () => {
				const val = this.building_field.get_value();
				this.building = val || null;
				this._maybe_load();
			},
		});

		this.cadence_field = this.page.add_field({
			fieldname: "cadence",
			label: __("Cadence"),
			fieldtype: "Select",
			options: SC_CADENCE_OPTIONS.join("\n"),
			change: () => {
				const val = this.cadence_field.get_value();
				this.cadence = val || null;
				this._maybe_load();
			},
		});

		this.page.set_primary_action(
			__("Submit Round"),
			() => this.submit_round(),
			"check"
		);
	}

	_maybe_load() {
		this.tasks = [];
		this.rows = {};
		if (this.building && this.cadence) {
			this.load_tasks();
		} else {
			this._render_empty(__("Pick a building and a cadence to build the checklist."));
		}
	}

	load_tasks() {
		this._render_loading();
		frappe.call({
			method: "apex_habitat.habitat.api.safety_checklist.get_tasks_for_cadence",
			args: { building: this.building, cadence: this.cadence },
			callback: (r) => {
				if (r.exc || !r.message) {
					this._render_error(
						__("Could not load the checklist. Please try again."),
						() => this.load_tasks()
					);
					return;
				}
				this.tasks = r.message.tasks || [];
				this._render_checklist();
			},
			error: () => {
				this._render_error(
					__("Could not load the checklist. Please try again."),
					() => this.load_tasks()
				);
			},
		});
	}

	submit_round() {
		if (!this.building || !this.cadence) {
			frappe.show_alert({
				message: __("Pick a building and a cadence to build the checklist."),
				indicator: "orange",
			});
			return;
		}
		if (!this.tasks.length) {
			frappe.show_alert({
				message: __("There are no checklist tasks to submit."),
				indicator: "orange",
			});
			return;
		}

		const lines = this.tasks.map((task) => {
			const row = this.rows[task.name] || {};
			return {
				task: task.name,
				execution_status: row.status_field
					? row.status_field.get_value()
					: "Excellent",
				notes: row.note_field ? row.note_field.get_value() : null,
			};
		});

		frappe.call({
			method: "apex_habitat.habitat.api.safety_checklist.submit_round",
			args: {
				building: this.building,
				cadence: this.cadence,
				round_date: frappe.datetime.get_today(),
				lines: JSON.stringify(lines),
			},
			freeze: true,
			freeze_message: __("Submitting round…"),
			callback: (r) => {
				if (r.exc || !r.message) {
					// Errors thrown server-side (e.g. the duplicate-round guard)
					// arrive as a server message; frappe surfaces it. Add a
					// fallback alert so the user is never left without feedback.
					frappe.show_alert({
						message: __("Could not submit the round. Please try again."),
						indicator: "red",
					});
					return;
				}
				frappe.msgprint({
					title: __("Round Submitted"),
					indicator: "green",
					message: __("Round {0} submitted. Overall result: {1}.", [
						r.message.safety_round,
						__(r.message.overall_result),
					]),
				});
				this._reset();
			},
			// No custom error handler: let frappe show the server's thrown
			// message (the duplicate-round guard and validation messages) via
			// its default msgprint so the operator sees exactly what failed.
		});
	}

	_reset() {
		this.cadence = null;
		this.tasks = [];
		this.rows = {};
		if (this.cadence_field) {
			this.cadence_field.set_value("");
		}
		this._render_empty(__("Pick a building and a cadence to build the checklist."));
	}

	_render_empty(message) {
		this.$container.empty();
		$('<div class="sc-empty text-muted"></div>').text(message).appendTo(this.$container);
	}

	_render_loading() {
		this.$container.empty();
		$('<div class="sc-empty text-muted" aria-busy="true"></div>')
			.text(__("Loading checklist…"))
			.appendTo(this.$container);
	}

	_render_error(message, retry) {
		this.$container.empty();
		const $err = $('<div class="sc-error"></div>').appendTo(this.$container);
		$('<div class="sc-error-msg"></div>').text(message).appendTo($err);
		$('<button class="btn btn-sm btn-default sc-error-retry"></button>')
			.text(__("Retry"))
			.on("click", () => retry && retry())
			.appendTo($err);
	}

	_render_checklist() {
		this.$container.empty();
		this.rows = {};

		const $summary = $('<div class="sc-summary"></div>').appendTo(this.$container);
		$('<span class="sc-summary-title"></span>')
			.text(this.building)
			.appendTo($summary);
		$('<span class="sc-summary-counts"></span>')
			.text(__("{0} tasks", [this.tasks.length]))
			.appendTo($summary);

		if (!this.tasks.length) {
			this._render_empty(__("No safety tasks match this building and cadence."));
			return;
		}

		const $list = $('<div class="sc-rows"></div>').appendTo(this.$container);
		this.tasks.forEach((task) => this._render_row(task).appendTo($list));
	}

	_render_row(task) {
		const $row = $('<div class="sc-row"></div>');

		const $head = $('<div class="sc-row-head"></div>').appendTo($row);
		$('<span class="sc-row-title"></span>')
			.text(task.task_title || task.name)
			.appendTo($head);
		if (task.task_code) {
			$('<span class="sc-row-code text-muted"></span>')
				.text(task.task_code)
				.appendTo($head);
		}

		const $controls = $('<div class="sc-row-controls"></div>').appendTo($row);

		const $status_wrap = $('<div class="sc-row-status"></div>').appendTo($controls);
		const status_field = frappe.ui.form.make_control({
			df: {
				fieldname: `status_${task.name}`,
				label: __("Status"),
				fieldtype: "Select",
				options: SC_STATUS_OPTIONS.join("\n"),
				default: "Excellent",
			},
			parent: $status_wrap.get(0),
			render_input: true,
		});
		status_field.refresh();
		status_field.set_value("Excellent");

		const $note_wrap = $('<div class="sc-row-note"></div>').appendTo($controls);
		const note_field = frappe.ui.form.make_control({
			df: {
				fieldname: `note_${task.name}`,
				label: __("Note"),
				fieldtype: "Data",
			},
			parent: $note_wrap.get(0),
			render_input: true,
		});
		note_field.refresh();

		this.rows[task.name] = { status_field, note_field };
		return $row;
	}
}
