// Copyright (c) 2026, afmcoltd
import { call } from "@shared/call";

const API = "apex.salis.api.fleet_employee";

/* Every read here resolves the caller to their own Salis Driver on the server, so the client
   never sends an identity — and the one write validates the vehicle it was given against that
   binding before overwriting it with the bound one. Nothing in this file is a gate. */
const callApi = (method, opts = {}) => call(API + "." + method, opts);

export const getMyVehicle = () => callApi("get_my_vehicle");

/* One window for the whole portal. The home preview used to take the server defaults while the
   trips screen asked for ninety days, so the same list showed different trips depending on
   which screen you were on, with nothing on either saying so. */
export const TRIP_WINDOW = { days: 90, limit: 100 };
export const FUEL_WINDOW = { days: 90, limit: 30 };

export const getMyRecentTrips = () => callApi("get_my_recent_trips", { args: { ...TRIP_WINDOW } });
export const getFuelStations = () => callApi("get_fuel_stations");
export const getMyFuelRequests = () => callApi("get_my_fuel_requests", { args: { ...FUEL_WINDOW } });

export const submitFuelRequest = (args) =>
  callApi("submit_fuel_request", { args, type: "POST" });
