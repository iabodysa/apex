// Copyright (c) 2026, afmcoltd

export const TAB_KEYS = ["approval", "boarding", "route", "map"];

export const tabsFor = (wide) => (wide ? TAB_KEYS.filter((key) => key !== "map") : TAB_KEYS);
