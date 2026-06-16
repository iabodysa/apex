// [#tn9tob]
const CSRF = () => (typeof window !== "undefined" && window.csrf_token) || "";

export async function call(method, { args = null, type = "GET" } = {}) {
  const url = "/api/method/" + method;
  const opts = {
    method: type,
    headers: { "X-Frappe-CSRF-Token": CSRF(), "Content-Type": "application/json" },
    credentials: "same-origin",
  };
  let full = url;
  if (type === "GET" && args) {
    const q = new URLSearchParams(args).toString();
    full = url + (q ? "?" + q : "");
  } else if (args) {
    opts.body = JSON.stringify(args);
  }
  const res = await fetch(full, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json())._server_messages || detail; } catch (e) {}
    throw new Error(detail || ("HTTP " + res.status));
  }
  const data = await res.json();
  return data.message;
}
