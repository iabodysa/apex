/* Worker identity token.
 *
 * The worker is NOT a Frappe user — identity is a personal, unguessable token
 * carried in the URL: /masar?w=<token>. The server template (www/masar.html)
 * resolves the token and exposes it as window.masar_token; we also fall back to
 * parsing the query string directly. Every API call forwards this token so the
 * backend can resolve it server-side to exactly ONE Employee. The token is read
 * once here and reused — the client never holds or sends an employee id. */
function readToken() {
  if (typeof window !== "undefined" && window.masar_token) {
    return String(window.masar_token).trim();
  }
  try {
    const params = new URLSearchParams(window.location.search);
    return (params.get("w") || "").trim();
  } catch (e) {
    return "";
  }
}

export const TOKEN = readToken();
export const hasToken = !!TOKEN;
