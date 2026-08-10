// Copyright (c) 2026, afmcoltd

const LEGACY_DRIVER_PAYLOAD_PREFIX = "salis_portal_cache:";

export function purgePayloadStorage(storage, prefix) {
  if (!storage || !prefix) return;
  const doomed = [];
  try {
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key && key.startsWith(prefix)) doomed.push(key);
    }
    for (const key of doomed) storage.removeItem(key);
  } catch (e) {
  }
}

export function purgeDriverPayloadStorage(storage) {
  purgePayloadStorage(storage, LEGACY_DRIVER_PAYLOAD_PREFIX);
}
