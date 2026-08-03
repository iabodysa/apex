// Copyright (c) 2026, AFMCO and contributors
export const EXIT_FLAG = {
  1: "exit1_security_cleared",
  2: "exit2_logistics_cleared",
  3: "exit3_receiving_cleared",
};

export function exitCleared(delivery, n) {
  return !!delivery[EXIT_FLAG[n]];
}

export function nextExit(delivery) {
  for (let n = 1; n <= 3; n++) if (!exitCleared(delivery, n)) return n;
  return 0;
}

export function clearedCount(delivery) {
  let n = 0;
  for (let g = 1; g <= 3; g++) if (exitCleared(delivery, g)) n += 1;
  return n;
}

export function gates(delivery, label) {
  const next = nextExit(delivery);
  return [1, 2, 3].map((n) => ({
    n,
    label: label(n),
    state: exitCleared(delivery, n) ? "cleared" : n === next ? "current" : "waiting",
  }));
}
