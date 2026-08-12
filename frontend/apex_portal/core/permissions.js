export function normalizeCapabilities(values) {
  if (!Array.isArray(values) || values.some((value) => typeof value !== "string" || !value)) {
    throw new TypeError("Invalid capability: capabilities must be non-empty strings");
  }
  return Object.freeze([...new Set(values)].sort());
}

export function can(capability, capabilities) {
  return typeof capability === "string" && capabilities.includes(capability);
}
