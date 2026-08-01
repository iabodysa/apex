// Copyright (c) 2026, AFMCO and contributors
// [#t647-shared-call]
// The single API-call layer shared by every *_portal SPA, built on frappe-ui's
// frappeRequest (CSRF is signed from window.csrf_token, exposed by the www host
// page). Each portal imports from "@shared/call":
//   - configureApi()  → wire frappeRequest as the resourceFetcher (call once in
//     main.js so createResource() throughout the app signs its requests).
//   - call(method,{args,type}) → imperative one-off method call, returning the
//     endpoint's unwrapped `message`. Used where a portal needs a direct call
//     outside a createResource (fleet_portal/api.js, driver_portal push opt-in).
import { frappeRequest, setConfig } from "frappe-ui";

// A portal's language toggle is client-side, so `frappe.throw(_("…"))` used to
// resolve against the operator's stored User.language and an Arabic page could
// receive an English refusal. `_lang` is Frappe's own first-precedence language
// source (frappe/translate.py:37,46 reads frappe.form_dict._lang before the user
// and site values), and form_dict is filled from BOTH the query string and a JSON
// body — so setting it here covers every request every portal makes, for one
// request only, without touching the stored User.language.
//
// The value is read from <html lang>, which each portal's App.vue keeps in sync
// with its own toggle: one already-maintained source, and no portal-specific
// import in this shared file.
function currentLang() {
  try {
    return (document.documentElement.getAttribute("lang") || "").trim();
  } catch (e) {
    return "";
  }
}

// Merge `_lang` into whatever params the caller supplied, without mutating them.
function withLang(options) {
  const lang = currentLang();
  if (!lang) return options;
  return { ...options, params: { ...(options.params || {}), _lang: lang } };
}

// Wire frappe-ui's createResource() to sign every request via frappeRequest.
// Idempotent — safe to call once per SPA boot.
export function configureApi() {
  setConfig("resourceFetcher", (options) => frappeRequest(withLang(options)));
}

// call(method, { args, type }) -> the endpoint's `message`.
//   GET  -> args become query params
//   POST/PUT/DELETE -> args become the JSON body
export function call(method, { args = null, type = "GET" } = {}) {
  const opts = { url: "/api/method/" + method, method: type };
  // frappeRequest carries `params` as the query-string for GET and as the JSON
  // body for POST/PUT/DELETE (the same split the old hand-rolled helper did).
  if (args) opts.params = args;
  // Resolves to the unwrapped `message` and rejects with a frappe-ui error.
  return frappeRequest(withLang(opts));
}
