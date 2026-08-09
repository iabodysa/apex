// Copyright (c) 2026, afmcoltd

export function createMapFitPolicy() {
  let pending = true;
  return {
    get pending() {
      return pending;
    },
    request() {
      pending = true;
    },
    resolve(hasGeometry) {
      if (hasGeometry) pending = false;
    },
  };
}
