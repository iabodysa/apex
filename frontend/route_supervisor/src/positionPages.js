// Copyright (c) 2026, afmcoltd

export function nextPositionStart(page) {
  return Number(page?.start || 0) + Number(page?.page_length || 0);
}

export function mergePositionPages(pages) {
  const merged = [];
  const positions = new Map();

  for (const page of [...pages].sort((a, b) => a.start - b.start)) {
    for (const row of page.positions || []) {
      const index = positions.get(row.dispatch_trip);
      if (index === undefined) {
        positions.set(row.dispatch_trip, merged.length);
        merged.push(row);
      } else {
        merged[index] = row;
      }
    }
  }
  return merged;
}
