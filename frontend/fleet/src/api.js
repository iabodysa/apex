// Copyright (c) 2026, afmcoltd
import { call } from "@shared/call";

const API = "apex.salis.api.fleet_employee";

const callApi = (method, opts = {}) => call(API + "." + method, opts);

export const getMyVehicle = () => callApi("get_my_vehicle");

export const TRIP_WINDOW = { days: 90, limit: 100 };
export const FUEL_WINDOW = { days: 90, limit: 30 };

export const getMyRecentTrips = () => callApi("get_my_recent_trips", { args: { ...TRIP_WINDOW } });
export const getFuelStations = () => callApi("get_fuel_stations");
export const getMyFuelRequests = () => callApi("get_my_fuel_requests", { args: { ...FUEL_WINDOW } });

export const submitFuelRequest = (args) =>
  callApi("submit_fuel_request", { args, type: "POST" });
