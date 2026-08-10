// Copyright (c) 2026, afmcoltd
frappe.provide("apex.desk");

apex.desk.newest_only = function (owner, key) {
	owner[key] = (owner[key] || 0) + 1;
	const ticket = owner[key];
	return function () {
		return owner[key] === ticket;
	};
};

apex.desk.lock_dialog_action = function (dialog, locked) {
	dialog.get_primary_btn().prop("disabled", locked).toggleClass("disabled", locked);
};
