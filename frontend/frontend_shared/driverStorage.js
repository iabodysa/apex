// Copyright (c) 2026, AFMCO and contributors

const LEGACY_DRIVER_PAYLOAD_PREFIX = "salis_portal_cache:";

export function purgeDriverPayloadStorage(storage) {
  if (!storage) return;
  const doomed = [];
  try {
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key && key.startsWith(LEGACY_DRIVER_PAYLOAD_PREFIX)) doomed.push(key);
    }
    for (const key of doomed) storage.removeItem(key);
  } catch (e) {
    // Storage can be blocked in private mode. Driver data never depends on it.
  }
}
