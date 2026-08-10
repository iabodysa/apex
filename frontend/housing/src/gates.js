// Copyright (c) 2026, afmcoltd
export const EXIT_FLAG = {
  1: "exit1_security_cleared",
  3: "exit3_receiving_cleared",
};

// The two sides of a hand-over, in order. The numbers are the stored field numbers,
// not positions, so the retired middle checkpoint leaves no gap to reason about.
export const EXIT_ORDER = [1, 3];

export function exitCleared(delivery, n) {
  return !!delivery[EXIT_FLAG[n]];
}

export function nextExit(delivery) {
  for (const n of EXIT_ORDER) if (!exitCleared(delivery, n)) return n;
  return 0;
}

export function clearedCount(delivery) {
  return EXIT_ORDER.filter((n) => exitCleared(delivery, n)).length;
}

export function gates(delivery, label) {
  const next = nextExit(delivery);
  return EXIT_ORDER.map((n) => ({
    n,
    label: label(n),
    state: exitCleared(delivery, n) ? "cleared" : n === next ? "current" : "waiting",
  }));
}
