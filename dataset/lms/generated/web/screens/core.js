// Modules 1 and 2: calendar, own account, user management.

import { get, patch, post } from "../api.js";
import {
  BOOLEAN_FILTER,
  button,
  choices,
  definitionList,
  field,
  fmtBool,
  fmtDate,
  fmtDateTime,
  form,
  h,
  pagedTable,
  replace,
  section,
  table,
} from "../ui.js";

// ---- LIB-UI-CAL-01 ---------------------------------------------------------------

const REASONS = { weekend: "weekend", holiday: "holiday" };

const calendarScreen = {
  id: "cal-01",
  title: "Calendar",
  module: "Core",
  roles: ["all"],
  async render(ctx) {
    const holidaysBox = h("div", { class: "holidays" });
    const dayLine = h("p", { class: "day-line" });

    async function loadHolidays(year) {
      try {
        const data = await get("/calendar/holidays", { year });
        replace(
          holidaysBox,
          table({
            caption: `Official holidays ${data.year}`,
            columns: [
              { label: "Date", value: (r) => fmtDate(r.date) },
              { label: "Holiday", value: (r) => r.name },
            ],
            rows: data.holidays,
          }),
        );
      } catch (error) {
        ctx.fail(error);
      }
    }

    const year = field({ name: "year", label: "Year", type: "number", value: ctx.today.slice(0, 4), min: 1900, max: 2100 });
    const yearForm = form({
      fields: [year],
      submit: "Show holidays",
      label: "Holidays of a year",
      onSubmit: (v) => {
        ctx.clearMessages();
        return loadHolidays(v.year.trim());
      },
    });

    const date = field({ name: "date", label: "Date", type: "date", value: ctx.today });
    async function showDay() {
      const value = date.input.value;
      if (!value) {
        replace(dayLine, "");
        return;
      }
      try {
        const data = await get(`/calendar/days/${encodeURIComponent(value)}`);
        replace(
          dayLine,
          `${fmtDate(data.date)} is `,
          h("strong", {}, data.working_day ? "a working day" : `not a working day (${REASONS[data.reason] || data.reason})`),
        );
      } catch (error) {
        replace(dayLine, "");
        ctx.fail(error);
      }
    }
    date.input.addEventListener("change", () => {
      ctx.clearMessages();
      showDay();
    });

    const days = field({ name: "days", label: "Days", type: "number", value: "1", min: 1, max: 365 });
    const start = field({ name: "start", label: "Start", type: "date", value: ctx.today });
    const end = field({ name: "end", label: "End", type: "date", value: ctx.today });

    const tools = h(
      "div",
      { class: "tools" },
      h("div", { class: "actions" }, button("Next working day", async () => {
        const result = await ctx.act(
          () => get("/calendar/next-working-day", { date: date.input.value }),
          (r) => `Next working day on or after ${date.input.value}: ${fmtDate(r.date)}`,
        );
        return result;
      })),
      h(
        "div",
        { class: "inline-form" },
        days,
        button("Add working days", () =>
          ctx.act(
            () => get("/calendar/add-working-days", { date: date.input.value, days: days.input.value.trim() }),
            (r) => `${date.input.value} + ${days.input.value.trim()} working days: ${fmtDate(r.date)}`,
          ),
        ),
      ),
      h(
        "div",
        { class: "inline-form" },
        start,
        end,
        button("Count working days", () =>
          ctx.act(
            () => get("/calendar/working-days-between", { start: start.input.value, end: end.input.value }),
            (r) => `Working days between ${start.input.value} and ${end.input.value}: ${r.working_days}`,
          ),
        ),
      ),
    );

    replace(
      ctx.body,
      section("Holidays", yearForm, holidaysBox),
      section("Working days", date, dayLine, tools),
    );
    await Promise.all([loadHolidays(year.input.value), showDay()]);
  },
};

// ---- LIB-UI-ACCT-01 --------------------------------------------------------------

const accountScreen = {
  id: "acct-01",
  title: "My account",
  module: "Identity and access",
  roles: ["all"],
  async render(ctx) {
    const facts = h("div", { class: "account-data" });
    async function load() {
      const me = await get("/auth/me");
      replace(
        facts,
        definitionList([
          ["Email", me.email],
          ["Full name", me.full_name],
          ["Role", me.role],
          ["Active", fmtBool(me.is_active)],
          ["Created", fmtDateTime(me.created_at)],
          ["Last login", fmtDateTime(me.last_login_at)],
        ]),
      );
    }
    const current = field({ name: "current_password", label: "Current password", type: "password", autocomplete: "current-password" });
    const next = field({ name: "new_password", label: "New password", type: "password", autocomplete: "new-password", hint: "8–128 characters with at least one letter and one digit." });
    const node = form({
      fields: [current, next],
      submit: "Change password",
      label: "Change password",
      async onSubmit(v) {
        const done = await ctx.act(
          () => post("/auth/change-password", { current_password: v.current_password, new_password: v.new_password }),
          "Password changed.",
          load,
        );
        if (done !== undefined) {
          current.input.value = "";
          next.input.value = "";
        }
      },
    });
    replace(ctx.body, section("Account data", facts), section("Change password", node));
    await load();
  },
};

// ---- LIB-UI-USR-01 ---------------------------------------------------------------

const ROLES = ["member", "librarian", "admin"];

const usersScreen = {
  id: "usr-01",
  title: "Users",
  module: "Identity and access",
  roles: ["admin"],
  desk: true,
  async render(ctx) {
    const filterRole = field({ name: "role", label: "Role", options: choices(ROLES, { any: "Any" }) });
    const filterActive = field({ name: "is_active", label: "Active", options: BOOLEAN_FILTER });
    const filterQ = field({ name: "q", label: "Search" });
    const editor = h("div", { class: "editor" });

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "ID", value: (u) => String(u.id) },
        { label: "Email", value: (u) => u.email },
        { label: "Full name", value: (u) => u.full_name },
        { label: "Role", value: (u) => u.role },
        { label: "Active", value: (u) => fmtBool(u.is_active) },
        { label: "Last login", value: (u) => fmtDateTime(u.last_login_at) },
        { label: "Actions", value: (u) => button("Edit", () => openEditor(u)) },
      ],
      load: (page) =>
        get("/users", { page, page_size: 20, role: filterRole.input.value, is_active: filterActive.input.value, q: filterQ.input.value.trim() }),
    });

    const filters = form({
      fields: [filterRole, filterActive, filterQ],
      submit: "Filter",
      label: "User filters",
      cls: "filters",
      onSubmit: () => {
        ctx.clearMessages();
        list.goTo(1);
      },
    });

    const email = field({ name: "email", label: "Email", type: "email" });
    const fullName = field({ name: "full_name", label: "Full name" });
    const role = field({ name: "role", label: "Role", options: choices(["librarian", "admin"]) });
    const password = field({ name: "password", label: "Password", type: "password", autocomplete: "new-password", hint: "8–128 characters with at least one letter and one digit." });
    const createForm = form({
      fields: [email, fullName, role, password],
      submit: "Create",
      label: "Create user",
      async onSubmit(v) {
        const created = await ctx.act(
          () => post("/users", { email: v.email.trim(), full_name: v.full_name.trim(), role: v.role, password: v.password }),
          (u) => `User ${u.email} created.`,
          () => list.reload(),
        );
        if (created) {
          email.input.value = "";
          fullName.input.value = "";
          password.input.value = "";
        }
      },
    });

    function openEditor(user) {
      const roleOptions = choices(user.role === "member" ? ROLES : ["librarian", "admin"]);
      const name = field({ name: "full_name", label: "Full name", value: user.full_name });
      const roleField = field({ name: "role", label: "Role", options: roleOptions, value: user.role });
      const active = field({
        name: "is_active",
        label: "Active",
        options: [{ value: "true", label: "Yes" }, { value: "false", label: "No" }],
        value: String(user.is_active),
      });
      const save = (v) =>
        ctx.act(
          () => patch(`/users/${user.id}`, { full_name: v.full_name.trim(), role: v.role, is_active: v.is_active === "true" }),
          (u) => `User ${u.email} saved.`,
          async (u) => {
            await list.reload();
            openEditor(u);
          },
        );
      const editForm = form({
        fields: [name, roleField, active],
        submit: "Save",
        label: "Change user",
        onSubmit(v) {
          if (user.is_active && v.is_active === "false") {
            ctx.ask({ text: `Deactivate user ${user.email}? Their sessions end immediately.`, onConfirm: () => save(v) });
          } else {
            save(v);
          }
        },
      });
      const newPassword = field({ name: "new_password", label: "New password", type: "password", autocomplete: "new-password" });
      const resetForm = form({
        fields: [newPassword],
        submit: "Reset password",
        label: "Reset password",
        async onSubmit(v) {
          const done = await ctx.act(() => post(`/users/${user.id}/reset-password`, { new_password: v.new_password }), `Password of ${user.email} reset.`);
          if (done !== undefined) newPassword.input.value = "";
        },
      });
      replace(
        editor,
        section(`Change user ${user.email}`, editForm, resetForm, button("Close", () => replace(editor))),
      );
      editor.scrollIntoView?.({ block: "nearest" });
    }

    replace(ctx.body, section("Create user", createForm), section("User list", filters, list.el), editor);
    await list.goTo(1);
  },
};

export const coreScreens = [calendarScreen, accountScreen, usersScreen];
