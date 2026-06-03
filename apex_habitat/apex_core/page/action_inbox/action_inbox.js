// Action Inbox — a single "pending my action" desk feed (Apex Core).
//
// Two sections render the aggregation read API
// (apex_habitat.apex_core.worklist.action_inbox.get_pending_actions):
//   • Pending Approvals — native Workflow Actions awaiting THIS user. Each card
//     lazily fetches the document's allowed transitions and renders one button
//     per transition; clicking it applies the workflow inline.
//   • Assigned Tasks — the user's open ToDos that point at a real document, each
//     with Open / Close.
//
// Native Frappe primitives ONLY (no Vue, no external libs). The page never writes
// through a custom endpoint: inline Approve/Reject goes through the canonical
// native pair frappe.model.workflow.get_transitions / apply_workflow, and a task
// is closed via frappe.client.set_value. Every interpolated value is escaped.

frappe.pages['action-inbox'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Action Inbox'),
		single_column: true,
	});
	wrapper.action_inbox = new ActionInbox(page);
};

class ActionInbox {
	constructor(page) {
		this.page = page;
		// CRITICAL: build EVERY container first so no render method ever touches an
		// undefined this.$x (a TypeError that node --check cannot catch). One skeleton,
		// all containers, before any render or fetch runs.
		this._build_skeleton();
		this.page.set_primary_action(__('Refresh'), () => this.refresh(), 'refresh');
		// Auto-refresh: any notification (a new approval/assignment lands as one) nudges
		// a debounced refresh so the feed never goes stale while the user watches it.
		frappe.realtime.on(
			'notification',
			frappe.utils.debounce(() => this.refresh(), 1000)
		);
		this.refresh();
	}

	_build_skeleton() {
		this.$root = $('<div class="action-inbox"></div>').appendTo(this.page.main);

		// Approvals section: header + body (cards) + its own empty placeholder.
		this.$approvalsSection = $('<section class="ai-section ai-section--approvals"></section>').appendTo(this.$root);
		$('<header class="ai-section-head"></header>').text(__('Pending Approvals')).appendTo(this.$approvalsSection);
		this.$approvals = $('<div class="ai-list ai-approvals"></div>').appendTo(this.$approvalsSection);

		// Tasks section: header + body (cards).
		this.$tasksSection = $('<section class="ai-section ai-section--tasks"></section>').appendTo(this.$root);
		$('<header class="ai-section-head"></header>').text(__('Assigned Tasks')).appendTo(this.$tasksSection);
		this.$tasks = $('<div class="ai-list ai-tasks"></div>').appendTo(this.$tasksSection);

		// A single page-level empty state shown only when BOTH sections are empty.
		this.$empty = $('<div class="ai-empty text-muted"></div>').appendTo(this.$root);
	}

	refresh() {
		this._render_loading();
		frappe
			.call('apex_habitat.apex_core.worklist.action_inbox.get_pending_actions')
			.then((r) => this._render((r && r.message) || {}))
			.catch(() => this._render_error());
	}

	// ---------- render ----------
	_render(data) {
		const workflow_actions = data.workflow_actions || [];
		const todos = data.todos || [];

		this.$approvals.empty();
		this.$tasks.empty();

		// Section visibility: an empty section hides its header (no bare "Pending
		// Approvals" over nothing); the page-level empty state covers the both-empty case.
		const hasApprovals = workflow_actions.length > 0;
		const hasTasks = todos.length > 0;
		this.$approvalsSection.toggle(hasApprovals);
		this.$tasksSection.toggle(hasTasks);

		if (!hasApprovals && !hasTasks) {
			this.$empty.text(__('Nothing awaiting your action.')).show();
			return;
		}
		this.$empty.empty().hide();

		workflow_actions.forEach((row) => this._workflow_card(row));
		todos.forEach((row) => this._todo_card(row));
	}

	_render_loading() {
		// Reuse the empty slot as a transient status line (the sections clear on render).
		this.$approvalsSection.hide();
		this.$tasksSection.hide();
		this.$empty.text(__('Loading…')).show();
	}

	_render_error() {
		this.$approvalsSection.hide();
		this.$tasksSection.hide();
		this.$empty.empty().show();
		$('<div class="ai-error-msg"></div>').text(__('Could not load your inbox. Please retry.')).appendTo(this.$empty);
		$('<button class="btn btn-default btn-sm"></button>')
			.text(__('Retry'))
			.on('click', () => this.refresh())
			.appendTo(this.$empty);
	}

	// ---------- Pending Approvals (Workflow Action) ----------
	_workflow_card(row) {
		const $card = $('<div class="ai-card ai-card--workflow"></div>').appendTo(this.$approvals);

		const $head = $('<div class="ai-card-head"></div>').appendTo($card);
		$('<span class="indicator-pill no-indicator-dot blue"></span>')
			.text(row.reference_doctype || '')
			.appendTo($head);
		// The document, as a link that opens its form.
		$('<a class="ai-card-link" href="#"></a>')
			.text(row.reference_name || '')
			.on('click', (e) => {
				e.preventDefault();
				frappe.set_route('Form', row.reference_doctype, row.reference_name);
			})
			.appendTo($head);

		const $meta = $('<div class="ai-card-meta text-muted"></div>').appendTo($card);
		$('<span class="ai-card-state"></span>')
			.text(__('State: {0}', [row.workflow_state || '']))
			.appendTo($meta);

		// Lazily resolve the allowed transitions for THIS document, then render one
		// button per transition. Native endpoint — the source of truth for what the
		// user may do next (it already honours the workflow's role/conditions).
		const $actions = $('<div class="ai-card-actions"></div>').appendTo($card);
		$('<span class="ai-actions-load text-muted"></span>').text(__('Loading actions…')).appendTo($actions);
		frappe
			.xcall('frappe.model.workflow.get_transitions', {
				doc: { doctype: row.reference_doctype, name: row.reference_name },
			})
			.then((transitions) => this._render_transitions($actions, $card, row, transitions || []))
			.catch(() => {
				$actions.empty();
				$('<span class="ai-actions-none text-muted"></span>')
					.text(__('No actions available.'))
					.appendTo($actions);
			});
	}

	_render_transitions($actions, $card, row, transitions) {
		$actions.empty();
		if (!transitions.length) {
			$('<span class="ai-actions-none text-muted"></span>').text(__('No actions available.')).appendTo($actions);
			return;
		}
		transitions.forEach((t) => {
			const action = t.action || '';
			// Destructive transitions (reject / cancel) read as danger; everything
			// else is a primary move. Match the action NAME, not a translated label.
			const danger = /reject|cancel/i.test(action);
			const cls = danger ? 'btn-danger' : 'btn-primary';
			$(`<button class="btn btn-sm ${cls} ai-action-btn"></button>`)
				.text(__(action))
				.on('click', () => this._apply_workflow($card, row, action))
				.appendTo($actions);
		});
	}

	_apply_workflow($card, row, action) {
		frappe.dom.freeze(__('Applying…'));
		frappe
			.xcall('frappe.model.workflow.apply_workflow', {
				doc: { doctype: row.reference_doctype, name: row.reference_name },
				action,
			})
			.then((doc) => {
				// A null return means the submit was queued in the background; either way
				// the action took, so confirm, retire this card, and re-check the empties.
				frappe.show_alert({ message: __('{0} applied', [__(action)]), indicator: 'green' });
				if (doc) {
					this._remove_card($card);
				} else {
					this.refresh();
				}
			})
			.catch(() => {
				frappe.show_alert({ message: __('Could not apply {0}', [__(action)]), indicator: 'red' });
				this.refresh();
			})
			.finally(() => frappe.dom.unfreeze());
	}

	// ---------- Assigned Tasks (ToDo) ----------
	_todo_card(row) {
		const $card = $('<div class="ai-card ai-card--todo"></div>').appendTo(this.$tasks);

		const $head = $('<div class="ai-card-head"></div>').appendTo($card);
		$('<span class="indicator-pill no-indicator-dot orange"></span>').text(__('Task')).appendTo($head);
		$('<a class="ai-card-link" href="#"></a>')
			.text(`${row.reference_doctype || ''}: ${row.reference_name || ''}`)
			.on('click', (e) => {
				e.preventDefault();
				frappe.set_route('Form', row.reference_doctype, row.reference_name);
			})
			.appendTo($head);

		if (row.description) {
			$('<div class="ai-card-desc"></div>').html(frappe.utils.escape_html(row.description)).appendTo($card);
		}

		const $meta = $('<div class="ai-card-meta text-muted"></div>').appendTo($card);
		if (row.priority) {
			$('<span class="ai-card-priority"></span>').text(__('Priority: {0}', [row.priority])).appendTo($meta);
		}
		if (row.date) {
			$('<span class="ai-card-date"></span>').text(__('Due: {0}', [row.date])).appendTo($meta);
		}

		const $actions = $('<div class="ai-card-actions"></div>').appendTo($card);
		$('<button class="btn btn-sm btn-default ai-action-btn"></button>')
			.text(__('Open'))
			.on('click', () => frappe.set_route('Form', row.reference_doctype, row.reference_name))
			.appendTo($actions);
		$('<button class="btn btn-sm btn-primary ai-action-btn"></button>')
			.text(__('Close'))
			.on('click', () => this._close_todo($card, row))
			.appendTo($actions);
	}

	_close_todo($card, row) {
		frappe.dom.freeze(__('Closing…'));
		frappe
			.xcall('frappe.client.set_value', {
				doctype: 'ToDo',
				name: row.name,
				fieldname: 'status',
				value: 'Closed',
			})
			.then(() => {
				frappe.show_alert({ message: __('Task closed'), indicator: 'green' });
				this.refresh();
			})
			.catch(() => {
				frappe.show_alert({ message: __('Could not close the task'), indicator: 'red' });
				this.refresh();
			})
			.finally(() => frappe.dom.unfreeze());
	}

	// Fade a retired card out, then drop it and re-check whether the inbox is now
	// empty (so the both-empty placeholder appears without a full re-fetch).
	_remove_card($card) {
		$card.fadeOut(200, () => {
			$card.remove();
			this._recheck_empty();
		});
	}

	_recheck_empty() {
		const hasApprovals = this.$approvals.children('.ai-card').length > 0;
		const hasTasks = this.$tasks.children('.ai-card').length > 0;
		this.$approvalsSection.toggle(hasApprovals);
		this.$tasksSection.toggle(hasTasks);
		if (!hasApprovals && !hasTasks) {
			this.$empty.text(__('Nothing awaiting your action.')).show();
		}
	}
}
