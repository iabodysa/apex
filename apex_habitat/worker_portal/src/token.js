// Copyright (c) 2026, AFMCO and contributors
// [#s7slet]
// [T-705/T-685] The personal token is NO LONGER readable by the SPA: it rides in
// the httpOnly `masar_wt` cookie (set server-side from the one-time ?w= hit) and
// the worker endpoints read it server-side. So the client sends NO token in its
// API calls — `TOKEN` is intentionally empty and kept only so existing call sites
// (`params: { token: TOKEN }`) compile; an empty token simply lets the server fall
// back to the cookie. The shell still needs to know whether a link is present to
// choose between the app and the "no link" state: the host page inlines that as a
// boolean (window.masar_has_token), with a legacy ?w= fallback for a not-yet-built
// shell. The raw secret is never exposed to JS, so an XSS cannot exfiltrate it.
function detectHasToken() {
  if (typeof window !== "undefined" && typeof window.masar_has_token === "boolean") {
    return window.masar_has_token;
  }
  // Legacy fallback: a ?w= still in the URL on first paint (before the redirect).
  try {
    return !!(new URLSearchParams(window.location.search).get("w") || "").trim();
  } catch (e) {
    return false;
  }
}

// Sent verbatim as the `token` param on API calls. Empty by design: the server
// reads the httpOnly cookie when no token arg is supplied.
export const TOKEN = "";
export const hasToken = detectHasToken();
