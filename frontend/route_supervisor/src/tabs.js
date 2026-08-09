// Copyright (c) 2026, afmcoltd

/* The four views of one plan, in the order the menu and the tab control both read them. Held
   apart from the router so the views can name a tab without importing the module that imports
   them back. */
export const TAB_KEYS = ["approval", "boarding", "route", "map"];

/* Above this width the live map is a pane beside the plan, so offering it as a tab as well
   would light a tab over a panel that is already on screen twice. */
export const tabsFor = (wide) => (wide ? TAB_KEYS.filter((key) => key !== "map") : TAB_KEYS);
