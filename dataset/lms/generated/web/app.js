// Entry point: routing by hash (LIB-UI-GEN-03), login, header and menu.

import { get, health, post, session } from "./api.js";
import { createContext } from "./context.js";
import { allScreens, menuGroups } from "./screens/index.js";
import { homeScreen } from "./screens/home.js";
import { loginScreen } from "./screens/login.js";
import { alertContent, button, clear, h, link, replace, setErrorReporter } from "./ui.js";

const main = document.getElementById("main");
const header = document.getElementById("app-header");
const menu = document.getElementById("menu");

let renderTicket = 0;
let unreadTicket = 0;

export function parseRoute(hash) {
  const raw = (hash || "").replace(/^#\/?/, "");
  const [id, ...rest] = raw.split("/");
  return { id: (id || "").toLowerCase(), param: rest.join("/") ? decodeURIComponent(rest.join("/")) : "" };
}

function allowed(screen, user) {
  return screen.roles.includes("all") || screen.roles.includes(user.role);
}

function screenById(id) {
  if (id === "home") return homeScreen;
  // screens marked "Part of …" have no route (LIB-UI-GEN-03)
  return allScreens.find((s) => s.id === id && !s.part) || null;
}

// ---- header and menu -------------------------------------------------------------

async function refreshUnread(user) {
  const slot = header.querySelector(".unread");
  if (!slot || user.role !== "member" || !user.member_id) return;
  const mine = (unreadTicket += 1);
  try {
    const data = await get(`/members/${user.member_id}/notifications/unread-count`);
    if (mine === unreadTicket) replace(slot, "Unread notifications: ", h("strong", {}, String(data.unread)));
  } catch {
    // the count is a convenience only; errors are shown by the screens themselves
  }
}

function renderHeader(user) {
  header.hidden = false;
  replace(
    header,
    h("span", { class: "app-title" }, "Library Management System"),
    h(
      "div",
      { class: "user-box" },
      h("span", { class: "user-name" }, user.full_name),
      h("span", { class: "user-role" }, user.role),
      user.role === "member" ? h("a", { class: "unread", href: "#/not-01" }) : null,
      button("Log out", logout),
    ),
  );
  refreshUnread(user);
}

function renderMenu(user) {
  menu.hidden = false;
  const nav = h("div", { class: "menu-groups" }, link("Home", "#/home", { class: "menu-home" }));
  for (const group of menuGroups) {
    const visible = group.screens.filter((s) => !s.part && allowed(s, user));
    if (!visible.length) continue;
    nav.append(
      h(
        "section",
        { class: "menu-group", "data-group": group.title },
        h("h2", {}, group.title),
        h("ul", {}, visible.map((s) => h("li", {}, link(s.title, `#/${s.id}`)))),
      ),
    );
  }
  replace(menu, nav);
  markCurrent();
}

function markCurrent() {
  const { id } = parseRoute(location.hash);
  for (const a of menu.querySelectorAll("a")) {
    if (a.getAttribute("href") === `#/${id}`) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
}

async function logout() {
  try {
    await post("/auth/logout");
  } catch {
    // the local session is removed in any case
  }
  session.clear();
  session.clearReturnTo();
  go("#/login");
}

function go(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

function hideChrome() {
  header.hidden = true;
  menu.hidden = true;
  clear(header);
  clear(menu);
}

// ---- screens ---------------------------------------------------------------------

function simpleScreen(title, ...children) {
  replace(main, h("h1", {}, title), ...children);
}

async function currentUser() {
  const stored = session.user();
  if (stored) return stored;
  const user = await get("/auth/me");
  session.setUser(user);
  return user;
}

async function route() {
  const ticket = (renderTicket += 1);
  const { id, param } = parseRoute(location.hash);

  if (!session.token()) {
    hideChrome();
    if (id !== "login") {
      session.setReturnTo(location.hash || "#/home");
      location.replace("#/login");
      return;
    }
    showLogin();
    return;
  }
  if (id === "login") {
    location.replace("#/home");
    return;
  }
  if (!id) {
    location.replace("#/home");
    return;
  }

  let user;
  try {
    user = await currentUser();
  } catch {
    if (ticket === renderTicket && session.token()) {
      // 401 already redirected to the login screen; other failures show the message
      hideChrome();
      simpleScreen("Library Management System", h("div", { role: "alert", class: "alert" }, alertContent(null)));
    }
    return;
  }
  if (ticket !== renderTicket) return;
  renderHeader(user);
  renderMenu(user);

  const screen = screenById(id);
  if (!screen) {
    simpleScreen("Not found", h("p", {}, "This screen does not exist."));
    return;
  }
  if (!allowed(screen, user)) {
    simpleScreen("Not allowed", h("p", {}, "You do not have access to this screen."));
    return;
  }

  let today;
  try {
    today = (await health()).today;
  } catch {
    today = new Date().toISOString().slice(0, 10); // only if /health fails; the screen reports its own errors
  }
  if (ticket !== renderTicket) return;

  const ctx = createContext({ user, today, main, param, refreshHeader: () => refreshUnread(user) });
  setErrorReporter((error) => ctx.fail(error));
  ctx.screens = allScreens.filter((s) => !s.part && allowed(s, user));
  ctx.h1 = h("h1", {}, screen.title);
  ctx.mount();
  main.focus({ preventScroll: true });
  window.scrollTo?.(0, 0);
  try {
    await screen.render(ctx);
  } catch (error) {
    if (ticket === renderTicket) ctx.fail(error);
  }
}

function showLogin() {
  const ctx = createContext({ user: { role: "anonymous" }, today: "", main, param: "", refreshHeader: null });
  setErrorReporter((error) => ctx.fail(error));
  ctx.h1 = h("h1", {}, loginScreen.title);
  ctx.mount();
  loginScreen.render(ctx, {
    onLoggedIn(token, user) {
      session.set(token, user);
      const target = session.returnTo() || "#/home";
      session.clearReturnTo();
      const next = parseRoute(target).id === "login" ? "#/home" : target;
      go(next);
    },
  });
}

document.addEventListener("lms:unauthorized", () => {
  if (!session.token()) return;
  const current = location.hash;
  session.clear();
  session.setReturnTo(parseRoute(current).id === "login" ? "#/home" : current || "#/home");
  go("#/login");
});

window.addEventListener("hashchange", () => {
  route();
  markCurrent();
});

route();
