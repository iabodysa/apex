// Copyright (c) 2026, afmcoltd
import { frappeRequest, setConfig } from "frappe-ui";

function currentLang() {
  try {
    return (document.documentElement.getAttribute("lang") || "").trim();
  } catch (e) {
    return "";
  }
}

function withLang(options) {
  const lang = currentLang();
  if (!lang) return options;
  return { ...options, params: { ...(options.params || {}), _lang: lang } };
}

export function configureApi() {
  setConfig("resourceFetcher", (options) => frappeRequest(withLang(options)));
}

export function call(method, { args = null, type = "GET" } = {}) {
  const opts = { url: "/api/method/" + method, method: type };
  if (args) opts.params = args;
  return frappeRequest(withLang(opts));
}
