// Custody Kiosk — POS-style custody issuing (v0.9.0).
//
// Standard Frappe page. No SPA / Vue / React / external libraries: built from
// frappe.ui.Page primitives + native DOM + jQuery (shipped with Frappe). The
// catalog comes from the single whitelisted reader get_kiosk_catalog (no N+1);
// the only write routes through the Custody Issue controller via issue_cart,
// which submits a real Custody Issue whose on_submit posts to the Accommodation
// Stock Ledger. The server is the source of truth: on success we clear the cart
// and re-fetch the catalog rather than mutating ledger state on the client.

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
		this.employee = null;
		this.building = null;
		this.articles = [];
		// article docname -> {article, article_name, uom, qty}
		this.cart = {};
	}

	setup() {
		this._setup_controls();
		this._build_layout();
		this._render_empty(__("Select an employee, then tap items to issue."));
		this._render_cart();
	}

	_setup_controls() {
		this.employee_field = this.page.add_field({
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
			reqd: 1,
			change: () => {
				this.employee = this.employee_field.get_value() || null;
			},
		});

		this.building_field = this.page.add_field({
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Accommodation Building",
			reqd: 1,
			change: () => {
				const val = this.building_field.get_value() || null;
				if (val !== this.building) {
					this.building = val;
					this.refresh();
				}
			},
		});

		this.page.set_primary_action(
			__("Refresh"),
			() => this.refresh(),
			"refresh"
		);
	}

	_build_layout() {
		this.$layout = $('<div class="ck-layout"></div>').appendTo(this.page.main);

		// Left — catalog (search + tile grid).
		const $catalog = $('<div class="ck-catalog"></div>').appendTo(this.$layout);
		const $tools = $('<div class="ck-tools"></div>').appendTo($catalog);
		this.$search = $(
			`<input type="search" class="ck-search form-control" placeholder="${frappe.utils.escape_html(
				__("Search articles…")
			)}">`
		).appendTo($tools);
		this.$search.on("input", () => this._render_tiles());
		this.$tiles = $('<div class="ck-tiles"></div>').appendTo($catalog);

		// Right — cart panel.
		const $cart = $('<div class="ck-cart"></div>').appendTo(this.$layout);
		$('<div class="ck-cart-header"></div>').text(__("Cart")).appendTo($cart);
		this.$cart_lines = $('<div class="ck-cart-lines"></div>').appendTo($cart);
		const $footer = $('<div class="ck-cart-footer"></div>').appendTo($cart);
		this.$issue_btn = $(
			`<button class="btn btn-primary btn-lg ck-issue-btn"></button>`
		)
			.text(__("Issue"))
			.appendTo($footer);
		this.$issue_btn.on("click", () => this._issue());
	}

	refresh() {
		if (!this.building) {
			this._render_empty(__("Select a building to load the catalog."));
			return;
		}
		frappe.call({
			method: "apex_habitat.habitat.api.custody_kiosk.get_kiosk_catalog",
			args: { building: this.building },
			freeze: true,
			freeze_message: __("Loading catalog…"),
			callback: (r) => {
				if (r.exc || !r.message) return;
				this.articles = r.message.articles || [];
				this._render_tiles();
			},
		});
	}

	_render_empty(message) {
		this.$tiles.empty();
		$('<div class="ck-empty text-muted"></div>').text(message).appendTo(this.$tiles);
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

	_render_tile(art) {
		const $tile = $(
			`<div class="ck-tile" tabindex="0" role="button"></div>`
		);

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

	_initials(name) {
		const parts = String(name || "").trim().split(/\s+/).slice(0, 2);
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

	_change_qty(article, delta) {
		const line = this.cart[article];
		if (!line) return;
		line.qty += delta;
		if (line.qty <= 0) {
			delete this.cart[article];
		}
		this._render_cart();
	}

	_render_cart() {
		this.$cart_lines.empty();
		const lines = Object.values(this.cart);

		if (!lines.length) {
			$('<div class="ck-cart-empty text-muted"></div>')
				.text(__("Cart is empty."))
				.appendTo(this.$cart_lines);
			this.$issue_btn.prop("disabled", true);
			return;
		}

		this.$issue_btn.prop("disabled", false);

		lines.forEach((line) => {
			const $line = $('<div class="ck-cart-line"></div>').appendTo(this.$cart_lines);
			$('<div class="ck-cart-line-name"></div>')
				.text(line.article_name)
				.appendTo($line);

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
				if (r.exc || !r.message) return;
				frappe.show_alert({
					message: __("Issued to {0}: {1}", [
						this.employee,
						r.message.custody_issue,
					]),
					indicator: "green",
				});
				this.cart = {};
				this._render_cart();
				this.refresh();
			},
		});
	}
}
