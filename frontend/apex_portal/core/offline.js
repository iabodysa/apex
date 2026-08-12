const DRAFT_ROOT = "apex:draft";
const ACTIVE_ROOT = "apex:draft-subject";

function identityPart(value, name) {
  if (typeof value !== "string" || !value || value.includes(":")) {
    throw new TypeError(`${name} must be a non-empty opaque value without colons`);
  }
  return value;
}

export function createDraftStore({ storage, site, entry, subjectScope }) {
  const identity = [
    identityPart(site, "site"),
    identityPart(entry, "entry"),
    identityPart(subjectScope, "subjectScope"),
  ].join(":");
  const prefix = `${DRAFT_ROOT}:${identity}:`;
  const activeKey = `${ACTIVE_ROOT}:${site}:${entry}`;

  return Object.freeze({
    activate() {
      const prior = storage.getItem(activeKey);
      if (prior && prior !== subjectScope) {
        const priorPrefix = `${DRAFT_ROOT}:${site}:${entry}:${prior}:`;
        const keys = Array.from({ length: storage.length }, (_, index) => storage.key(index));
        for (const key of keys) {
          if (key?.startsWith(priorPrefix)) storage.removeItem(key);
        }
      }
      storage.setItem(activeKey, subjectScope);
    },
    read(formKey) {
      const value = storage.getItem(prefix + identityPart(formKey, "formKey"));
      return value === null ? null : JSON.parse(value);
    },
    write(formKey, value) {
      storage.setItem(prefix + identityPart(formKey, "formKey"), JSON.stringify(value));
    },
    clear(formKey) {
      storage.removeItem(prefix + identityPart(formKey, "formKey"));
    },
  });
}

export function isCacheablePortalAsset({
  url,
  method,
  contentType,
  origin = globalThis.location?.origin ?? "https://apex.invalid",
}) {
  if (method !== "GET") return false;
  let resource;
  try {
    resource = new URL(url, origin);
  } catch {
    return false;
  }
  if (resource.origin !== new URL(origin).origin) return false;
  const { pathname } = resource;
  if (pathname.startsWith("/api/") || contentType?.includes("text/html")) return false;
  if (!pathname.startsWith("/assets/apex/")) return false;
  return /(?:javascript|css|font|woff|image)/i.test(contentType ?? "");
}
