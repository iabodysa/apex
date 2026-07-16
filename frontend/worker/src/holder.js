// Copyright (c) 2026, AFMCO and contributors
//
// Holder-type discriminator for the ONE merged Masar portal. Both entry pages load
// this single bundle: /masar (worker barcode entry) and /driver (driver barcode
// entry). Each www template projects window.holder_type ("Worker" | "Driver") — the
// only thing the two entries differ by — so the SPA mounts exactly that type's
// screen set and bottom nav (a worker never sees driver options, and vice-versa).
//
// The raw token is NEVER exposed here: it rides in the httpOnly cookie (masar_wt for
// workers, masar_dt for drivers) and every apex.salis.api.* endpoint resolves the
// holder server-side from that cookie. The client only learns which TYPE it is.
const RAW = (typeof window !== "undefined" && window.holder_type) || "";

// Default to Worker when the flag is absent (a bare /masar render), so the safest
// (token-gated worker) shell loads rather than the driver one.
export const HOLDER_TYPE = RAW === "Driver" ? "Driver" : "Worker";
export const IS_DRIVER = HOLDER_TYPE === "Driver";
export const IS_WORKER = HOLDER_TYPE === "Worker";
