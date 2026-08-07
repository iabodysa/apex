// Copyright (c) 2026, afmcoltd
const RAW = (typeof window !== "undefined" && window.holder_type) || "";

export const HOLDER_TYPE = RAW === "Driver" ? "Driver" : "Worker";
export const IS_DRIVER = HOLDER_TYPE === "Driver";
export const IS_WORKER = HOLDER_TYPE === "Worker";
