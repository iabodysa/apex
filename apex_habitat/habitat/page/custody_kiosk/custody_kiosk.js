// [#qt2p0p]

frappe.pages["custody-kiosk"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Custody Kiosk"),
		single_column: true,
	});

	const kiosk = new CustodyKiosk(page);
	kiosk.setup();
};

class CustodyKiosk {
	constructor(page) {
		this.page = page;
		// [#mode01]
		this.mode = "issue";
		// Issue-mode state
		this.employee = null;
		this.building = null;
		this.articles = [];
		// Return-mode state
		this.party_type = "Employee";
		this.party = null;
		this.held = [];
		// [#kwkz4i]
		this.cart = {};
		this.return_cart = {};
	}

	setup() {
		this._setup_controls();
		this._build_layout();
		this._apply_mode();
	}

	_setup_controls() {
		// Issue-mode fields
		this.employee_field = this.page.add_field({
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
			change: () => {
				this.employee = this.employee_field.get_value() || null;
			},
		});

		this.building_field = this.page.add_field({
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Accommodation Building",
			change: () => {
				const val = this.building_field.get_value() || null;
				if (val !== this.building) {
					this.building = val;
					this.refresh();
				}
			},
		});

		// [#party01]
		this.party_type_field = this.page.add_field({
			fieldname: "party_type",
			label: __("Worker Type"),
			fieldtype: "Select",
			options: ["Employee", "Temporary Worker"],
			default: "Employee",
			change: () => {
				const val = this.party_type_field.get_value() || "Employee";
				if (val !== this.party_type) {
					this.party_type = val;
					this.party = null;
					this.party_field.set_value("");
					this._update_party_options();
					this.return_cart = {};
					this._render_held_empty(__("Select a worker to load held custody."));
					this._render_cart();
				}
			},
		});

		this.party_field = this.page.add_field({
			fieldname: "party",
			label: __("Worker"),
			fieldtype: "Link",
			options: "Employee",
			change: () => {
				const val = this.party_field.get_value() || null;
				if (val !== this.party) {
					this.party = val;
					this.return_cart = {};
					this.refresh();
				}
			},
		});

		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
	}

	_update_party_options() {
		// [#party02]
		const target = this.party_type === "Temporary Worker" ? "Temporary Worker" : "Employee";
		this.party_field.df.options = target;
		this.party_field.set_value("");
	}

	_build_layout() {
		this.$layout = $('<div class="ck-layout"></div>').appendTo(this.page.main);

		// [#modeui]
		const $modebar = $(
			`<div class="ck-modebar" role="tablist" aria-label="${frappe.utils.escape_html(
				__("Issue or return mode")
			)}"></div>`
		).appendTo(this.page.main);
		// Mode bar must sit ABOVE the catalog/cart layout.
		$modebar.insertBefore(this.$layout);

		this.$mode_issue = $(
			`<button class="ck-mode-btn" role="tab" type="button"></button>`
		)
			.text(__("Issue Custody"))
			.appendTo($modebar)
			.on("click", () => this._set_mode("issue"));
		this.$mode_return = $(
			`<button class="ck-mode-btn" role="tab" type="button"></button>`
		)
			.text(__("Return"))
			.appendTo($modebar)
			.on("click", () => this._set_mode("return"));

		// [#20cz3t]
		const $catalog = $('<div class="ck-catalog"></div>').appendTo(this.$layout);
		const $tools = $('<div class="ck-tools"></div>').appendTo($catalog);
		this.$search = $(
			`<input type="search" class="ck-search form-control" placeholder="${frappe.utils.escape_html(
				__("Search articles…")
			)}" aria-label="${frappe.utils.escape_html(__("Search articles"))}">`
		).appendTo($tools);
		// [#guxhpt]
		let search_timer = null;
		this.$search.on("input", () => {
			clearTimeout(search_timer);
			search_timer = setTimeout(() => this._render_visible(), 120);
		});
		this.$tiles = $('<div class="ck-tiles"></div>').appendTo($catalog);

		// [#4232vl]
		const $cart = $('<div class="ck-cart"></div>').appendTo(this.$layout);
		this.$cart_header = $('<div class="ck-cart-header"></div>')
			.text(__("Cart"))
			.appendTo($cart);
		this.$cart_lines = $('<div class="ck-cart-lines"></div>').appendTo($cart);
		const $footer = $('<div class="ck-cart-footer"></div>').appendTo($cart);
		this.$action_btn = $(
			`<button class="btn btn-primary btn-lg ck-action-btn"></button>`
		)
			.text(__("Issue"))
			.appendTo($footer);
		this.$action_btn.on("click", () => this._commit());
	}

	// [#modeset]
	_set_mode(mode) {
		if (mode === this.mode) return;
		this.mode = mode;
		this._apply_mode();
	}

	_apply_mode() {
		const is_return = this.mode === "return";

		// Toggle the tablist visual + ARIA state (aria-pressed for a toggle pair).
		this.$mode_issue
			.toggleClass("active", !is_return)
			.attr("aria-pressed", String(!is_return))
			.attr("aria-selected", String(!is_return));
		this.$mode_return
			.toggleClass("active", is_return)
			.attr("aria-pressed", String(is_return))
			.attr("aria-selected", String(is_return));

		// Show the fields that belong to this mode, hide the others.
		this._toggle_field(this.employee_field, !is_return);
		this._toggle_field(this.building_field, !is_return);
		this._toggle_field(this.party_type_field, is_return);
		this._toggle_field(this.party_field, is_return);

		// The catalog search filters articles in both modes.
		this.$cart_header.text(is_return ? __("Return cart") : __("Cart"));
		this.$action_btn.text(is_return ? __("Return") : __("Issue"));

		if (is_return) {
			if (!this.party) {
				this._render_held_empty(__("Select a worker to load held custody."));
			} else {
				this.refresh();
			}
		} else {
			if (!this.building) {
				this._render_empty(__("Select a building to load the catalog."));
			} else {
				this._render_tiles();
			}
		}
		this._render_cart();
	}

	_toggle_field(field, show) {
		if (!field || !field.$wrapper) return;
		field.$wrapper.toggle(!!show);
	}

	refresh() {
		if (this.mode === "return") {
			this._refresh_held();
			return;
		}
		if (!this.building) {
			this._render_empty(__("Select a building to load the catalog."));
			return;
		}
		this._render_loading();
		frappe.call({
			method: "apex_habitat.habitat.api.custody_kiosk.get_kiosk_catalog",
			args: { building: this.building },
			callback: (r) => {
				if (r.exc || !r.message) {
					this._render_error(__("Could not load the catalog."), () => this.refresh());
					return;
				}
				this.articles = r.message.articles || [];
				this._render_tiles();
			},
			error: () => {
				this._render_error(__("Could not load the catalog."), () => this.refresh());
			},
		});
	}

	// [#heldload]
	_refresh_held() {
		if (!this.party) {
			this._render_held_empty(__("Select a worker to load held custody."));
			return;
		}
		this._render_loading();
		frappe.call({
			method: "apex_habitat.habitat.api.custody_kiosk.get_party_custody",
			args: { party_type: this.party_type, party: this.party },
			callback: (r) => {
				if (r.exc || !r.message) {
					this._render_error(__("Could not load held custody."), () => this.refresh());
					return;
				}
				this.held = r.message.lines || [];
				this._render_held();
			},
			error: () => {
				this._render_error(__("Could not load held custody."), () => this.refresh());
			},
		});
	}

	_render_visible() {
		if (this.mode === "return") {
			this._render_held();
		} else {
			this._render_tiles();
		}
	}

	_render_empty(message) {
		this.$tiles.empty();
		$('<div class="ck-empty text-muted"></div>').text(message).appendTo(this.$tiles);
	}

	_render_held_empty(message) {
		this.held = [];
		this._render_empty(message);
	}

	_render_loading() {
		this.$tiles.empty();
		// [#3omcm3]
		for (let i = 0; i < 6; i++) {
			const $sk = $('<div class="ck-tile ck-tile-skeleton" aria-hidden="true"></div>');
			$('<div class="ck-tile-thumb ck-skel"></div>').appendTo($sk);
			$('<div class="ck-skel ck-skel-line"></div>').appendTo($sk);
			$('<div class="ck-skel ck-skel-line ck-skel-line-sm"></div>').appendTo($sk);
			$sk.appendTo(this.$tiles);
		}
	}

	_render_error(message, retry) {
		this.$tiles.empty();
		const $box = $('<div class="ck-error"></div>').appendTo(this.$tiles);
		$('<div class="ck-error-msg text-danger"></div>').text(message).appendTo($box);
		$('<button class="btn btn-default btn-sm ck-retry"></button>')
			.text(__("Retry"))
			.appendTo($box)
			.on("click", () => retry());
	}

	_render_tiles() {
		this.$tiles.empty();
		const term = (this.$search.val() || "").trim().toLowerCase();
		const list = this.articles.filter((a) => {
			if (!term) return true;
			return (a.article_name || "").toLowerCase().indexOf(term) !== -1;
		});

		if (!list.length) {
			this._render_empty(__("No articles found."));
			return;
		}

		list.forEach((art) => {
			this._render_tile(art).appendTo(this.$tiles);
		});
	}

	// [#heldtiles]
	_render_held() {
		this.$tiles.empty();
		const term = (this.$search.val() || "").trim().toLowerCase();
		const list = this.held.filter((l) => {
			if (!term) return true;
			return (l.article_name || "").toLowerCase().indexOf(term) !== -1;
		});

		if (!list.length) {
			this._render_empty(
				this.held.length
					? __("No articles found.")
					: __("This worker holds no returnable custody.")
			);
			return;
		}

		list.forEach((line) => {
			this._render_held_tile(line).appendTo(this.$tiles);
		});
	}

	_render_tile(art) {
		const $tile = $(`<div class="ck-tile" tabindex="0" role="button"></div>`);

		const $thumb = $('<div class="ck-tile-thumb"></div>').appendTo($tile);
		if (art.image) {
			$('<img class="ck-tile-img">')
				.attr("src", art.image)
				.attr("alt", art.article_name || art.article)
				.appendTo($thumb);
		} else {
			$('<div class="ck-tile-initials"></div>')
				.text(this._initials(art.article_name || art.article))
				.appendTo($thumb);
		}

		$('<div class="ck-tile-name"></div>')
			.text(art.article_name || art.article)
			.appendTo($tile);

		const meta = [];
		if (art.uom) meta.push(art.uom);
		if (art.store_balance !== null && art.store_balance !== undefined) {
			meta.push(__("In stock: {0}", [art.store_balance]));
		}
		if (meta.length) {
			$('<div class="ck-tile-meta"></div>').text(meta.join(" · ")).appendTo($tile);
		}

		const add = () => this._add_to_cart(art);
		$tile.on("click", add);
		$tile.on("keydown", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				add();
			}
		});
		return $tile;
	}

	// [#heldtile]
	_render_held_tile(line) {
		const $tile = $(`<div class="ck-tile" tabindex="0" role="button"></div>`);

		const $thumb = $('<div class="ck-tile-thumb"></div>').appendTo($tile);
		$('<div class="ck-tile-initials"></div>')
			.text(this._initials(line.article_name || line.article))
			.appendTo($thumb);

		$('<div class="ck-tile-name"></div>')
			.text(line.article_name || line.article)
			.appendTo($tile);

		const meta = [];
		if (line.uom) meta.push(line.uom);
		meta.push(__("Held: {0}", [line.qty]));
		$('<div class="ck-tile-meta"></div>').text(meta.join(" · ")).appendTo($tile);

		// Each held line is tied to its source Custody Issue.
		$('<div class="ck-tile-sub text-muted"></div>')
			.text(__("Issue: {0}", [line.custody_issue]))
			.appendTo($tile);

		const add = () => this._add_held_to_cart(line);
		$tile.on("click", add);
		$tile.on("keydown", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				add();
			}
		});
		return $tile;
	}

	_initials(name) {
		const parts = String(name || "")
			.trim()
			.split(/\s+/)
			.slice(0, 2);
		return parts.map((p) => p.charAt(0).toUpperCase()).join("") || "?";
	}

	_add_to_cart(art) {
		const existing = this.cart[art.article];
		if (existing) {
			existing.qty += 1;
		} else {
			this.cart[art.article] = {
				article: art.article,
				article_name: art.article_name || art.article,
				uom: art.uom,
				qty: 1,
			};
		}
		this._render_cart();
	}

	// [#heldadd]
	_add_held_to_cart(line) {
		const key = `${line.custody_issue}::${line.article}`;
		const existing = this.return_cart[key];
		if (existing) {
			// Never let the return cart exceed the held quantity.
			if (existing.qty < line.qty) existing.qty += 1;
		} else {
			this.return_cart[key] = {
				key: key,
				custody_issue: line.custody_issue,
				article: line.article,
				article_name: line.article_name || line.article,
				uom: line.uom,
				qty: 1,
				max: line.qty,
			};
		}
		this._render_cart();
	}

	_change_qty(article, delta) {
		const line = this.cart[article];
		if (!line) return;
		line.qty += delta;
		if (line.qty <= 0) {
			delete this.cart[article];
		}
		this._render_cart();
	}

	// [#heldqty]
	_change_return_qty(key, delta) {
		const line = this.return_cart[key];
		if (!line) return;
		line.qty += delta;
		if (line.qty <= 0) {
			delete this.return_cart[key];
		} else if (line.max && line.qty > line.max) {
			line.qty = line.max;
		}
		this._render_cart();
	}

	_render_cart() {
		if (this.mode === "return") {
			this._render_return_cart();
			return;
		}
		this.$cart_lines.empty();
		const lines = Object.values(this.cart);

		if (!lines.length) {
			$('<div class="ck-cart-empty text-muted"></div>')
				.text(__("Cart is empty."))
				.appendTo(this.$cart_lines);
			this.$action_btn.prop("disabled", true);
			return;
		}

		this.$action_btn.prop("disabled", false);

		lines.forEach((line) => {
			const $line = $('<div class="ck-cart-line"></div>').appendTo(this.$cart_lines);
			$('<div class="ck-cart-line-name"></div>').text(line.article_name).appendTo($line);

			const $stepper = $('<div class="ck-stepper"></div>').appendTo($line);
			$('<button class="btn btn-default btn-sm ck-step ck-step-minus">−</button>')
				.appendTo($stepper)
				.on("click", () => this._change_qty(line.article, -1));
			$('<span class="ck-step-qty"></span>').text(line.qty).appendTo($stepper);
			$('<button class="btn btn-default btn-sm ck-step ck-step-plus">+</button>')
				.appendTo($stepper)
				.on("click", () => this._change_qty(line.article, 1));
		});
	}

	// [#retcart]
	_render_return_cart() {
		this.$cart_lines.empty();
		const lines = Object.values(this.return_cart);

		if (!lines.length) {
			$('<div class="ck-cart-empty text-muted"></div>')
				.text(__("Return cart is empty."))
				.appendTo(this.$cart_lines);
			this.$action_btn.prop("disabled", true);
			return;
		}

		this.$action_btn.prop("disabled", false);

		lines.forEach((line) => {
			const $line = $('<div class="ck-cart-line"></div>').appendTo(this.$cart_lines);
			const $info = $('<div class="ck-cart-line-info"></div>').appendTo($line);
			$('<div class="ck-cart-line-name"></div>').text(line.article_name).appendTo($info);
			$('<div class="ck-cart-line-sub text-muted"></div>')
				.text(line.custody_issue)
				.appendTo($info);

			const $stepper = $('<div class="ck-stepper"></div>').appendTo($line);
			$('<button class="btn btn-default btn-sm ck-step ck-step-minus">−</button>')
				.appendTo($stepper)
				.on("click", () => this._change_return_qty(line.key, -1));
			$('<span class="ck-step-qty"></span>').text(line.qty).appendTo($stepper);
			const $plus = $(
				'<button class="btn btn-default btn-sm ck-step ck-step-plus">+</button>'
			)
				.appendTo($stepper)
				.on("click", () => this._change_return_qty(line.key, 1));
			// Cap at the held quantity.
			$plus.prop("disabled", !!line.max && line.qty >= line.max);
		});
	}

	_commit() {
		if (this.mode === "return") {
			this._return();
			return;
		}
		this._issue();
	}

	_issue() {
		const lines = Object.values(this.cart);
		if (!this.employee) {
			frappe.show_alert({
				message: __("Select an employee before issuing."),
				indicator: "orange",
			});
			return;
		}
		if (!this.building) {
			frappe.show_alert({
				message: __("Select a building before issuing."),
				indicator: "orange",
			});
			return;
		}
		if (!lines.length) {
			frappe.show_alert({ message: __("Cart is empty."), indicator: "orange" });
			return;
		}

		const items = lines.map((l) => ({ article: l.article, qty: l.qty }));

		this.$action_btn.prop("disabled", true);
		frappe.call({
			method: "apex_habitat.habitat.api.custody_kiosk.issue_cart",
			args: {
				employee: this.employee,
				building: this.building,
				items_json: JSON.stringify(items),
			},
			freeze: true,
			freeze_message: __("Issuing…"),
			callback: (r) => {
				if (r.exc || !r.message) {
					// [#c7lpcm]
					frappe.show_alert({
						message: __("Could not issue the cart. Please review and try again."),
						indicator: "red",
					});
					this._render_cart();
					return;
				}
				frappe.show_alert({
					message: __("Issued to {0}: {1}", [this.employee, r.message.custody_issue]),
					indicator: "green",
				});
				this.cart = {};
				this._render_cart();
				this.refresh();
			},
			error: () => {
				frappe.show_alert({
					message: __("Could not issue the cart. Please review and try again."),
					indicator: "red",
				});
				this._render_cart();
			},
		});
	}

	// [#retcommit]
	_return() {
		const lines = Object.values(this.return_cart);
		if (!this.party) {
			frappe.show_alert({
				message: __("Select a worker before returning."),
				indicator: "orange",
			});
			return;
		}
		if (!lines.length) {
			frappe.show_alert({ message: __("Return cart is empty."), indicator: "orange" });
			return;
		}

		const items = lines.map((l) => ({
			custody_issue: l.custody_issue,
			article: l.article,
			qty: l.qty,
		}));

		this.$action_btn.prop("disabled", true);
		frappe.call({
			method: "apex_habitat.habitat.api.custody_kiosk.return_cart",
			args: {
				party_type: this.party_type,
				party: this.party,
				items_json: JSON.stringify(items),
			},
			freeze: true,
			freeze_message: __("Returning…"),
			callback: (r) => {
				if (r.exc || !r.message) {
					frappe.show_alert({
						message: __("Could not return the cart. Please review and try again."),
						indicator: "red",
					});
					this._render_cart();
					return;
				}
				const returns = r.message.custody_returns || [];
				frappe.show_alert({
					message: __("Returned from {0}: {1}", [this.party, returns.join(", ")]),
					indicator: "green",
				});
				this.return_cart = {};
				this._render_cart();
				this.refresh();
			},
			error: () => {
				frappe.show_alert({
					message: __("Could not return the cart. Please review and try again."),
					indicator: "red",
				});
				this._render_cart();
			},
		});
	}
}
