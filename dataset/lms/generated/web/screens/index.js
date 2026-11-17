// Registry of all screens. Later modules add their files here.

import { adminScreens } from "./admin.js";
import { catalogScreens } from "./catalog.js";
import { circulationScreens } from "./circulation.js";
import { coreScreens } from "./core.js";
import { discoveryScreens } from "./discovery.js";
import { memberScreens } from "./members.js";
import { roomScreens } from "./rooms.js";
import { equipmentScreens } from "./equipment.js";
import { digitalScreens } from "./digital.js";
import { interlibraryScreens } from "./ill.js";
import { staffScreens } from "./staff.js";
import { eventScreens } from "./events.js";
import { courseScreens } from "./courses.js";
import { donationScreens } from "./donations.js";
import { preservationScreens } from "./preservation.js";
import { inventoryScreens } from "./inventory.js";
import { suggestionScreens } from "./suggestions.js";
import { programScreens } from "./programs.js";
import { messagingScreens } from "./messaging.js";
import { accessScreens } from "./access.js";
import { printingScreens } from "./printing.js";

export const allScreens = [
  ...coreScreens,
  ...memberScreens,
  ...catalogScreens,
  ...circulationScreens,
  ...discoveryScreens,
  ...adminScreens,
  ...roomScreens,
  ...equipmentScreens,
  ...digitalScreens,
  ...interlibraryScreens,
  ...staffScreens,
  ...eventScreens,
  ...courseScreens,
  ...donationScreens,
  ...preservationScreens,
  ...inventoryScreens,
  ...suggestionScreens,
  ...programScreens,
  ...messagingScreens,
  ...accessScreens,
  ...printingScreens,
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
  "Study rooms",
  "Equipment loans",
  "Digital resources",
  "Interlibrary loans",
  "Staff and shifts",
  "Events",
  "Course reserves",
  "Donations",
  "Preservation",
  "Inventory counts",
  "Purchase suggestions",
  "Reading programs",
  "Announcements and messages",
  "Member cards and building access",
  "Printing and copying",
];

export const menuGroups = ORDER.map((title) => ({ title, screens: allScreens.filter((s) => s.module === title) }));
