// Registry of all screens. Later modules add their files here.

import { adminScreens } from "./admin.js";
import { catalogScreens } from "./catalog.js";
import { circulationScreens } from "./circulation.js";
import { coreScreens } from "./core.js";
import { discoveryScreens } from "./discovery.js";
import { memberScreens } from "./members.js";

export const allScreens = [
  ...coreScreens,
  ...memberScreens,
  ...catalogScreens,
  ...circulationScreens,
  ...discoveryScreens,
  ...adminScreens,
];

// Menu groups in the order of the modules; the group of a screen is its `module`.
const ORDER = [
  "Core",
  "Identity and access",
  "Members",
  "Catalog",
  "Loans and returns",
  "Reservations",
  "Fines and payments",
  "Notifications",
  "Search",
  "Reports",
  "Branches and transfers",
  "Purchasing",
  "Audit log and data",
];

export const menuGroups = ORDER.map((title) => ({ title, screens: allScreens.filter((s) => s.module === title) }));
