/**
 * The portal's translation lookup, reading the Arabic the server took from ar.csv.
 *
 * WHY THIS FILE EXISTS INSTEAD OF `window.__`. Frappe ships `__()` in both its desk and
 * website bundles, but only the desk shell ever fills the dictionary it reads:
 * `frappe/www/app.html:55` is the single line that assigns
 * `frappe._messages = frappe.boot["__messages"]`, and the website's own boot payload
 * (`frappe/website/utils.py:168-192`) carries no `__messages` key at all. This portal is a
 * standalone document — `apex_portal_app.html` closes its own `</body>`, so Frappe's
 * auto-extend at `frappe/website/page_renderers/template_page.py:199-204` is skipped and
 * no Frappe bundle loads. Calling `window.__` here would return English, silently, forever.
 *
 * So the server puts apex's own ar.csv on the page as a fourth JSON contract and this reads
 * it. The lookup is deliberately the same as Frappe's (`frappe/public/js/frappe/translate.js:9-19`):
 * the source string IS the key, a miss falls back to the source, and `{0}` placeholders are
 * substituted after the lookup so a translated string can reorder them.
 */

const CONTRACT_ID = "apex-portal-messages";

let messages = null;

function load(documentSource) {
  const element = documentSource?.getElementById(CONTRACT_ID);
  if (!element || element.getAttribute("type") !== "application/json") {
    // A missing contract is normal outside the served page — unit tests render components
    // with no document contract at all — and English is the correct answer there.
    return Object.freeze({});
  }
  try {
    const parsed = JSON.parse(element.textContent);
    return Object.freeze(parsed && typeof parsed === "object" ? parsed : {});
  } catch {
    return Object.freeze({});
  }
}

/** Reset the cache. Tests call this after swapping the document contract. */
export function resetMessages() {
  messages = null;
}

/**
 * Translate ``text``, substituting ``{0}``-style placeholders from ``replace``.
 *
 * Placeholders are substituted AFTER the lookup, never before, so an Arabic translation may
 * place them in a different order than the English source does.
 */
export function __(text, replace) {
  if (typeof text !== "string" || !text) {
    return text;
  }
  if (messages === null) {
    messages = load(globalThis.document);
  }
  const translated = messages[text] || text;
  if (!replace) {
    return translated;
  }
  return translated.replace(/{(\d+)}/g, (match, index) =>
    Object.hasOwn(replace, index) ? String(replace[index]) : match,
  );
}
