import { PORTAL_CONTEXTS } from "./router.js";
import { normalizeCapabilities } from "./permissions.js";

const CONTRACT_KEYS = new Set([
  "entry",
  "public_path",
  "initial_route",
  "capabilities",
  "site_name",
  "socketio_port",
  "async_enabled",
  "language",
  "subject_scope",
]);

function requireString(record, key) {
  if (typeof record[key] !== "string" || !record[key]) {
    throw new TypeError(`Portal bootstrap ${key} must be a non-empty string`);
  }
}

export function parsePortalBootstrap(source = globalThis.window?.apex_portal) {
  if (!source || typeof source !== "object" || Array.isArray(source)) {
    throw new TypeError("Portal bootstrap must be an object");
  }
  const unexpected = Object.keys(source).filter((key) => !CONTRACT_KEYS.has(key));
  if (unexpected.length) {
    throw new TypeError(`Portal bootstrap contains unexpected credential or field: ${unexpected.join(", ")}`);
  }

  for (const key of ["entry", "public_path", "initial_route", "site_name", "language", "subject_scope"]) {
    requireString(source, key);
  }
  if (!Number.isInteger(source.socketio_port) || source.socketio_port <= 0) {
    throw new TypeError("Portal bootstrap socketio_port must be a positive integer");
  }
  if (typeof source.async_enabled !== "boolean") {
    throw new TypeError("Portal bootstrap async_enabled must be boolean");
  }
  if (!/^[A-Za-z0-9_-]{8,128}$/.test(source.subject_scope)) {
    throw new TypeError("Portal bootstrap subject_scope must be opaque");
  }

  const context = PORTAL_CONTEXTS[source.entry];
  if (!context) throw new TypeError(`Unknown portal entry: ${source.entry}`);
  if (!context.publicPaths.includes(source.public_path)) {
    throw new TypeError(`Portal public_path does not match entry ${source.entry}`);
  }

  return Object.freeze({
    entry: source.entry,
    public_path: source.public_path,
    initial_route: source.initial_route,
    capabilities: normalizeCapabilities(source.capabilities),
    site_name: source.site_name,
    socketio_port: source.socketio_port,
    async_enabled: source.async_enabled,
    language: source.language,
    subject_scope: source.subject_scope,
  });
}
