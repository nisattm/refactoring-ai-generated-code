// Module 19: staff profiles, branch hours and closures, shift plan, own shifts, leave, staff reports (section 3.5).

import { clientError, fetchAll, get, patch, post, api, del } from "../api.js";
import {
  BOOLEAN_FILTER,
  anyOption,
  branchOptions,
  button,
  choices,
  definitionList,
  field,
  fieldProblems,
  fmtBool,
  fmtDate,
  fmtDateTime,
  fmtText,
  fmtTime,
  form,
  h,
  int,
  omitNull,
  pagedTable,
  recordOptions,
  replace,
  section,
  table,
  text,
  words,
} from "../ui.js";
import { branchMap, branchName } from "../views.js";

const MODULE = "Staff and shifts";
const EMPLOYMENT = ["full_time", "part_time"];
const LEAVE_KINDS = ["annual", "sick", "unpaid"];
const LEAVE_STATUSES = ["pending", "approved", "rejected", "cancelled"];
const SHIFT_STATUSES = ["planned", "cancelled", "completed", "missed"];
const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

// ---- dates (calendar arithmetic on the text of a date; the browser clock is not used) ----------

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const isDate = (value) => DATE_RE.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));
const toDate = (value) => new Date(`${value}T00:00:00Z`);
const isoDate = (date) => date.toISOString().slice(0, 10);

function addDays(value, days) {
  const date = toDate(value);
  date.setUTCDate(date.getUTCDate() + days);
  return isoDate(date);
}

const weekdayIndex = (value) => (toDate(value).getUTCDay() + 6) % 7; // Monday = 0
const mondayOf = (value) => addDays(value, -weekdayIndex(value));
const dayLabel = (value) => `${DAY_NAMES[weekdayIndex(value)]} ${value}`;
const lastOfMonth = (year, month) => isoDate(new Date(Date.UTC(year, month, 0)));

function needDate(name, value) {
  if (!isDate(value)) {
    throw clientError("VALIDATION_ERROR", "Enter a valid date.", { fields: [{ field: name, problem: "expected a valid date in the form YYYY-MM-DD" }] });
  }
  return value;
}

const timeField = (name, label, value, hint) =>
  field({ name, label, type: "time", value, step: "1800", hint });

const shiftTimes = (s) => `${s.start_time}–${s.end_time}`;
const activeBranchIds = (branches) => branches.filter((b) => b.is_active);

async function loadStaff() {
  return fetchAll("/staff");
}

const staffLabel = (s) => `${s.full_name} (${s.email})`;

// ---- LIB-UI-STF-01 ---------------------------------------------------------------

const staffScreen = {
  id: "stf-01",
  title: "Staff",
  module: MODULE,
  roles: ["admin"],
  async render(ctx) {
    const branches = await ctx.branches();
    const map = await branchMap(ctx);
    const editor = h("div", { class: "staff-editor" });
    const createBox = h("div", { class: "staff-create" });

    const homeFilter = field({ name: "home_branch_id", label: "Home branch", options: branchOptions(branches, { any: "Any" }) });
    const employmentFilter = field({ name: "employment", label: "Employment", options: choices(EMPLOYMENT, { any: "Any" }) });
    const activeFilter = field({ name: "is_active", label: "Active", options: BOOLEAN_FILTER });

    const deactivate = (profile) =>
      ctx.ask({
        text: `Deactivate ${profile.full_name}? Their planned shifts that start after now and their pending leave requests will be cancelled.`,
        onConfirm: () => ctx.act(() => patch(`/staff/${profile.id}`, { is_active: false }), "Staff profile deactivated.", reload),
      });

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "ID", value: (s) => String(s.id) },
        { label: "Name", value: (s) => s.full_name },
        { label: "Email", value: (s) => s.email },
        { label: "Home branch", value: (s) => branchName(map, s.home_branch_id) },
        { label: "Employment", value: (s) => words(s.employment) },
        { label: "Weekly hours", value: (s) => String(s.weekly_hours) },
        { label: "Annual leave days", value: (s) => String(s.annual_leave_days) },
        { label: "Started on", value: (s) => fmtDate(s.started_on) },
        { label: "Active", value: (s) => fmtBool(s.is_active) },
        {
          label: "Actions",
          value: (s) =>
            h(
              "div",
              { class: "row-actions" },
              button("Edit", () => openEditor(s)),
              s.is_active
                ? button("Deactivate", () => deactivate(s))
                : button("Activate", () => ctx.act(() => patch(`/staff/${s.id}`, { is_active: true }), "Staff profile activated.", reload)),
            ),
        },
      ],
      load: (page) =>
        get("/staff", {
          page,
          page_size: 20,
          home_branch_id: homeFilter.input.value,
          employment: employmentFilter.input.value,
          is_active: activeFilter.input.value,
        }),
    });

    const filters = form({
      fields: [homeFilter, employmentFilter, activeFilter],
      submit: "Filter",
      label: "Staff filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });

    const reload = async () => {
      replace(editor);
      await Promise.all([list.reload(), buildCreate()]);
    };

    function openEditor(profile) {
      const home = field({ name: "home_branch_id", label: "Home branch", options: branchOptions(branches), value: profile.home_branch_id });
      const employment = field({ name: "employment", label: "Employment", options: choices(EMPLOYMENT), value: profile.employment });
      const weekly = field({
        name: "weekly_hours",
        label: "Weekly hours",
        type: "number",
        value: profile.weekly_hours,
        min: 10,
        max: 40,
        hint: "Full time: 40; part time: 10–30.",
      });
      const leave = field({ name: "annual_leave_days", label: "Annual leave days", type: "number", value: profile.annual_leave_days, min: 0, max: 30, hint: "0–30." });
      const active = field({ name: "is_active", label: "Active", options: [{ value: "true", label: "Yes" }, { value: "false", label: "No" }], value: String(profile.is_active) });
      const node = form({
        fields: [home, employment, weekly, leave, active],
        submit: "Save",
        label: "Change staff profile",
        extra: button("Close", () => replace(editor)),
        onSubmit(v) {
          node.fieldErrors({});
          const body = omitNull({
            home_branch_id: Number(v.home_branch_id) !== profile.home_branch_id ? Number(v.home_branch_id) : null,
            employment: v.employment !== profile.employment ? v.employment : null,
            weekly_hours: int(v.weekly_hours) !== profile.weekly_hours ? int(v.weekly_hours) : null,
            annual_leave_days: int(v.annual_leave_days) !== profile.annual_leave_days ? int(v.annual_leave_days) : null,
            is_active: (v.is_active === "true") !== profile.is_active ? v.is_active === "true" : null,
          });
          const save = () =>
            ctx.act(
              () => patch(`/staff/${profile.id}`, body),
              "Staff profile saved.",
              reload,
              (error) => node.fieldErrors(fieldProblems(error)),
            );
          if (body.is_active === false) {
            ctx.ask({
              text: `Deactivate ${profile.full_name}? Their planned shifts that start after now and their pending leave requests will be cancelled.`,
              onConfirm: save,
            });
          } else {
            return save();
          }
        },
      });
      replace(editor, section(`Change staff profile: ${profile.full_name}`, node));
    }

    async function buildCreate() {
      const [users, profiles] = await Promise.all([fetchAll("/users", { is_active: "true" }), loadStaff()]);
      const taken = new Set(profiles.map((p) => p.user_id));
      const candidates = users.filter((u) => u.role !== "member" && !taken.has(u.id));
      const user = field({
        name: "user_id",
        label: "User",
        options: recordOptions(candidates, (u) => `${u.full_name} (${u.email})`),
        hint: candidates.length ? "Active librarians and admins without a profile." : "Every active librarian and admin already has a profile.",
      });
      const home = field({ name: "home_branch_id", label: "Home branch", options: branchOptions(activeBranchIds(branches)) });
      const employment = field({ name: "employment", label: "Employment", options: choices(EMPLOYMENT) });
      const weekly = field({ name: "weekly_hours", label: "Weekly hours", type: "number", min: 10, max: 40, hint: "Full time: 40 (default); part time: 10–30, required." });
      const leave = field({ name: "annual_leave_days", label: "Annual leave days", type: "number", min: 0, max: 30, hint: "0–30; default 14 (full time) or 7 (part time)." });
      const started = field({ name: "started_on", label: "Started on", type: "date", value: ctx.today, hint: "Not after today." });
      const node = form({
        fields: [user, home, employment, weekly, leave, started],
        submit: "Create",
        label: "Create staff profile",
        async onSubmit(v) {
          node.fieldErrors({});
          const created = await ctx.act(
            () =>
              post(
                "/staff",
                omitNull({
                  user_id: int(v.user_id),
                  home_branch_id: int(v.home_branch_id),
                  employment: v.employment,
                  weekly_hours: int(v.weekly_hours),
                  annual_leave_days: int(v.annual_leave_days),
                  started_on: text(v.started_on),
                }),
              ),
            (p) => `Staff profile of ${p.full_name} created.`,
            reload,
            (error) => node.fieldErrors(fieldProblems(error)),
          );
          return created;
        },
      });
      replace(createBox, section("Create staff profile", node));
    }

    replace(ctx.body, createBox, filters, list.el, editor);
    await Promise.all([list.goTo(1), buildCreate()]);
  },
};

// ---- LIB-UI-STF-02 ---------------------------------------------------------------

const hoursScreen = {
  id: "stf-02",
  title: "Branch hours and closures",
  module: MODULE,
  roles: ["all"],
  async render(ctx) {
    const branches = await ctx.branches();
    const preferred = activeBranchIds(branches)[0] || branches[0];
    const hoursBox = h("div", { class: "branch-hours" });
    const daysBox = h("div", { class: "open-days" });
    const closureAdd = h("div", { class: "closure-add" });
    const closureList = h("div", { class: "closure-list" });

    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches), value: preferred?.id });
    const year = field({ name: "year", label: "Year", type: "number", value: ctx.today.slice(0, 4), min: 1900, max: 2100 });
    const month = field({
      name: "month",
      label: "Month",
      options: MONTHS.map((label, i) => ({ value: String(i + 1), label })),
      value: String(Number(ctx.today.slice(5, 7))),
    });
    const branchId = () => Number(branch.input.value);

    let closures = null;
    function closureTable() {
      return pagedTable({
        onError: (e) => ctx.fail(e),
        columns: [
          { label: "Date", value: (c) => fmtDate(c.date) },
          { label: "Reason", value: (c) => c.reason },
          ...(ctx.isAdmin
            ? [
                {
                  label: "Actions",
                  value: (c) =>
                    c.date > ctx.today
                      ? button("Remove", () =>
                          ctx.ask({
                            text: `Remove the closure of ${fmtDate(c.date)}? Cancelled shifts and bookings are not restored.`,
                            onConfirm: () => ctx.act(() => del(`/closures/${c.id}`), "Closure removed.", reloadAll),
                          }),
                        )
                      : "–",
                },
              ]
            : []),
        ],
        load: (page) => get("/closures", { page, page_size: 20, branch_id: branchId() }),
      });
    }

    async function loadHours() {
      const data = await get(`/branches/${branchId()}/hours`);
      if (!ctx.isAdmin) {
        replace(hoursBox, section("Opening hours", definitionList([["Opens at", data.opens_at], ["Closes at", data.closes_at], ["Minimum staff", String(data.min_staff)]])));
        return;
      }
      const opens = timeField("opens_at", "Opens at", data.opens_at, "Minutes 00 or 30.");
      const closes = timeField("closes_at", "Closes at", data.closes_at, "At least 4 hours after opening.");
      const minStaff = field({ name: "min_staff", label: "Minimum staff", type: "number", value: data.min_staff, min: 1, max: 10, hint: "1–10 staff needed at every open moment." });
      const node = form({
        fields: [opens, closes, minStaff],
        submit: "Save",
        label: "Set opening hours",
        onSubmit(v) {
          node.fieldErrors({});
          return ctx.act(
            () => api("PUT", `/branches/${branchId()}/hours`, { body: { opens_at: v.opens_at, closes_at: v.closes_at, min_staff: int(v.min_staff) } }),
            "Opening hours saved.",
            reloadAll,
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      replace(hoursBox, section("Opening hours", node));
    }

    async function loadDays() {
      const y = String(year.input.value).trim();
      if (!/^\d{4}$/.test(y)) {
        throw clientError("VALIDATION_ERROR", "Enter a valid year.", { fields: [{ field: "year", problem: "expected a year" }] });
      }
      const m = Number(month.input.value);
      const from = `${y}-${String(m).padStart(2, "0")}-01`;
      const to = lastOfMonth(Number(y), m);
      const data = await get(`/branches/${branchId()}/open-days`, { from, to });
      replace(
        daysBox,
        section(
          `Open days: ${MONTHS[m - 1]} ${y}`,
          table({
            columns: [
              { label: "Date", value: (d) => dayLabel(d.date) },
              { label: "Open", value: (d) => fmtBool(d.open) },
              { label: "Reason", value: (d) => fmtText(d.reason) },
              { label: "Opens at", value: (d) => fmtText(d.opens_at) },
              { label: "Closes at", value: (d) => fmtText(d.closes_at) },
            ],
            rows: data.days,
            rowClass: (d) => (d.open ? undefined : "overdue"),
          }),
        ),
      );
    }

    function buildClosureAdd() {
      if (!ctx.isAdmin) return;
      const date = field({ name: "date", label: "Date", type: "date", hint: "A working day after today." });
      const reason = field({ name: "reason", label: "Reason", hint: "1–200 characters." });
      const node = form({
        fields: [date, reason],
        submit: "Add",
        label: "Add closure",
        async onSubmit(v) {
          node.fieldErrors({});
          const done = await ctx.act(
            () => post(`/branches/${branchId()}/closures`, { date: v.date, reason: v.reason.trim() }),
            (c) =>
              `Closure of ${fmtDate(c.date)} added. Cancelled shifts: ${c.cancelled_shifts}; room bookings: ${c.cancelled_room_bookings}; equipment reservations: ${c.cancelled_equipment_reservations}; events: ${c.cancelled_events ?? 0}.`,
            reloadAll,
            (error) => node.fieldErrors(fieldProblems(error)),
          );
          if (done) reason.input.value = "";
        },
      });
      replace(closureAdd, section("Add closure", node));
    }

    async function reloadAll() {
      await loadHours();
      await loadDays();
      closures = closureTable();
      replace(closureList, section("Closures", closures.el));
      await closures.goTo(1);
    }

    const chooser = form({
      fields: [branch, year, month],
      submit: "Show",
      label: "Choose branch and month",
      cls: "filters",
      async onSubmit() {
        ctx.clearMessages();
        try {
          await reloadAll();
        } catch (error) {
          ctx.fail(error);
        }
      },
    });
    buildClosureAdd();
    replace(ctx.body, chooser, hoursBox, daysBox, closureAdd, closureList);
    if (preferred) await reloadAll();
  },
};

// ---- LIB-UI-STF-03 ---------------------------------------------------------------

const shiftPlanScreen = {
  id: "stf-03",
  title: "Shift plan",
  module: MODULE,
  roles: ["admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const active = activeBranchIds(branches);
    const preferred = active[0] || branches[0];
    const staff = (await loadStaff()).filter((s) => s.is_active);
    const staffOptions = recordOptions(staff, staffLabel);

    const gridBox = h("div", { class: "week-grid" });
    const copyBox = h("div", { class: "copy-result" });
    const coverageBox = h("div", { class: "coverage" });
    const editor = h("div", { class: "shift-editor" });
    const planBox = h("div", { class: "shift-plan" });

    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches), value: preferred?.id });
    const week = field({ name: "week", label: "Week of", type: "date", value: mondayOf(ctx.today), hint: "Any date; the week Monday–Sunday is shown." });
    const coverageDate = field({ name: "date", label: "Date", type: "date", value: ctx.today });

    const branchId = () => Number(branch.input.value);
    const monday = () => mondayOf(needDate("week", week.input.value));

    async function loadCoverage() {
      const day = needDate("date", coverageDate.input.value);
      const data = await get("/reports/branch-coverage", { branch_id: branchId(), date: day });
      replace(
        coverageBox,
        section(
          `Coverage of ${dayLabel(day)}`,
          data.open
            ? h("p", {}, `Staff needed at every open moment: ${data.min_staff}.`)
            : h("p", {}, "The branch is not open on this date."),
          data.open
            ? table({
                columns: [
                  { label: "Slot", value: (s) => s.start },
                  { label: "Staff", value: (s) => String(s.staff) },
                  { label: "Covered", value: (s) => (s.ok ? "Yes" : h("strong", { class: "missing" }, "Missing")) },
                ],
                rows: data.slots,
                rowClass: (s) => (s.ok ? undefined : "overdue missing-slot"),
              })
            : null,
        ),
      );
    }

    async function loadWeek() {
      const first = monday();
      const last = addDays(first, 6);
      const [shifts, open, missing] = await Promise.all([
        fetchAll("/shifts", { branch_id: branchId(), from: first, to: last }),
        get(`/branches/${branchId()}/open-days`, { from: first, to: last }),
        get("/reports/branch-coverage", { branch_id: branchId(), from: first, to: last }),
      ]);
      const openBy = new Map(open.days.map((d) => [d.date, d]));
      const missingBy = new Map(missing.days.map((d) => [d.date, d.missing_slots]));
      const rows = Array.from({ length: 7 }, (_, i) => addDays(first, i));
      replace(
        gridBox,
        section(
          `Week ${first} – ${last}`,
          table({
            columns: [
              { label: "Day", value: (d) => dayLabel(d) },
              {
                label: "Branch",
                value: (d) => {
                  const o = openBy.get(d);
                  if (!o) return "–";
                  return o.open ? `Open ${o.opens_at}–${o.closes_at}` : `Closed (${o.reason})`;
                },
              },
              { label: "Missing slots", value: (d) => (missingBy.has(d) ? String(missingBy.get(d)) : "–") },
              {
                label: "Shifts",
                value: (d) => {
                  const day = shifts.filter((s) => s.date === d);
                  if (!day.length) return "No shifts";
                  return h(
                    "ul",
                    { class: "shift-list" },
                    day.map((s) =>
                      h(
                        "li",
                        { class: `shift shift-${s.status}` },
                        h("span", {}, `${shiftTimes(s)} ${s.staff_name} (${s.hours} h) – ${s.status}${s.cancel_reason ? `: ${words(s.cancel_reason)}` : ""}`),
                        s.status === "planned"
                          ? h("span", { class: "row-actions" }, button("Change", () => openEditor(s)), button("Cancel", () => cancelShift(s)))
                          : null,
                      ),
                    ),
                  );
                },
              },
            ],
            rows,
            rowClass: (d) => (missingBy.get(d) > 0 ? "overdue" : undefined),
          }),
        ),
      );
      await loadCoverage();
    }

    async function reload() {
      replace(editor);
      await loadWeek();
    }

    function cancelShift(shift) {
      ctx.ask({
        text: `Cancel the shift of ${shift.staff_name} on ${shift.date}, ${shiftTimes(shift)}?`,
        onConfirm: () => ctx.act(() => post(`/shifts/${shift.id}/cancel`), "Shift cancelled.", reload),
      });
    }

    function shiftFields(shift) {
      return {
        staff_id: field({ name: "staff_id", label: "Staff member", options: staffOptions, value: shift?.staff_id }),
        branch_id: field({ name: "branch_id", label: "Branch", options: branchOptions(active), value: shift?.branch_id ?? branchId() }),
        date: field({ name: "date", label: "Date", type: "date", value: shift?.date ?? monday() }),
        start_time: timeField("start_time", "Start", shift?.start_time ?? "09:00", "Minutes 00 or 30."),
        end_time: timeField("end_time", "End", shift?.end_time ?? "17:00", "2–10 hours long."),
      };
    }

    function openEditor(shift) {
      const f = shiftFields(shift);
      const node = form({
        fields: Object.values(f),
        submit: "Save",
        label: "Change shift",
        extra: button("Close", () => replace(editor)),
        onSubmit(v) {
          node.fieldErrors({});
          const body = omitNull({
            staff_id: Number(v.staff_id) !== shift.staff_id ? Number(v.staff_id) : null,
            branch_id: Number(v.branch_id) !== shift.branch_id ? Number(v.branch_id) : null,
            date: v.date !== shift.date ? v.date : null,
            start_time: v.start_time !== shift.start_time ? v.start_time : null,
            end_time: v.end_time !== shift.end_time ? v.end_time : null,
          });
          return ctx.act(
            () => patch(`/shifts/${shift.id}`, body),
            "Shift changed.",
            reload,
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      replace(editor, section(`Change shift of ${shift.staff_name}`, node));
    }

    function buildPlan() {
      const f = shiftFields(null);
      const node = form({
        fields: Object.values(f),
        submit: "Plan",
        label: "Plan a shift",
        onSubmit(v) {
          node.fieldErrors({});
          return ctx.act(
            () =>
              post("/shifts", {
                staff_id: int(v.staff_id),
                branch_id: int(v.branch_id),
                date: v.date,
                start_time: v.start_time,
                end_time: v.end_time,
              }),
            (s) => `Shift planned for ${s.staff_name} on ${s.date}, ${shiftTimes(s)}.`,
            loadWeek,
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      replace(planBox, section("Plan a shift", node));
    }

    async function copyLastWeek() {
      const to = monday();
      const from = addDays(to, -7);
      const result = await ctx.act(
        () => post("/shifts/copy-week", { branch_id: branchId(), from_week: from, to_week: to }),
        (r) => `Copied the shifts of ${from}: ${r.created} created, ${r.skipped.length} skipped.`,
        async (r) => {
          let sources = new Map();
          if (r.skipped.length) {
            try {
              const old = await fetchAll("/shifts", { branch_id: branchId(), from, to: addDays(from, 6) });
              sources = new Map(old.map((s) => [s.id, s]));
            } catch {
              sources = new Map();
            }
          }
          replace(
            copyBox,
            section(
              "Copy last week",
              h("p", {}, `Created: ${r.created}. Skipped: ${r.skipped.length}.`),
              r.skipped.length
                ? table({
                    columns: [
                      { label: "Source shift", value: (x) => String(x.source_shift_id) },
                      {
                        label: "Shift",
                        value: (x) => {
                          const s = sources.get(x.source_shift_id);
                          return s ? `${dayLabel(s.date)} ${shiftTimes(s)} ${s.staff_name}` : "–";
                        },
                      },
                      { label: "Reason", value: (x) => `${x.error_code} (${words(x.error_code).toLowerCase()})` },
                    ],
                    rows: r.skipped,
                  })
                : null,
            ),
          );
          await loadWeek();
        },
      );
      return result;
    }

    async function show() {
      ctx.clearMessages();
      replace(copyBox);
      try {
        await loadWeek();
      } catch (error) {
        ctx.fail(error);
      }
    }

    function shiftWeek(days) {
      week.input.value = addDays(monday(), days);
      replace(copyBox);
      return show();
    }

    const chooser = form({
      fields: [branch, week],
      submit: "Show",
      label: "Choose branch and week",
      cls: "filters",
      extra: [
        button("Week before", () => shiftWeek(-7)),
        button("Week after", () => shiftWeek(7)),
        button("Copy last week", copyLastWeek),
        button("Process", () =>
          ctx.act(() => post("/staff/process"), (r) => `Processed: ${r.missed} shifts marked missed, ${r.auto_checked_out} checked out automatically.`, loadWeek),
        ),
      ],
      onSubmit: show,
    });
    const coverageForm = form({
      fields: [coverageDate],
      submit: "Show coverage",
      label: "Coverage of a day",
      cls: "filters",
      async onSubmit() {
        ctx.clearMessages();
        try {
          await loadCoverage();
        } catch (error) {
          ctx.fail(error);
        }
      },
    });
    buildPlan();
    replace(ctx.body, chooser, gridBox, copyBox, editor, planBox, coverageForm, coverageBox);
    if (preferred) await loadWeek();
  },
};

// ---- LIB-UI-STF-04 ---------------------------------------------------------------

const myShiftsScreen = {
  id: "stf-04",
  title: "My shifts",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const me = await get("/staff/me");
    const map = await branchMap(ctx);
    const from = field({ name: "from", label: "From", type: "date", value: addDays(ctx.today, -14) });
    const to = field({ name: "to", label: "To", type: "date" });
    const status = field({ name: "status", label: "Status", options: choices(SHIFT_STATUSES, { any: "Any" }) });

    const checkedIn = (s) => s.status === "planned" && s.checked_in_at && !s.checked_out_at;
    const canCheckIn = (s) => s.status === "planned" && !s.checked_in_at && s.date === ctx.today;

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      rowClass: (s) => (s.status === "missed" ? "overdue" : undefined),
      columns: [
        { label: "Date", value: (s) => dayLabel(s.date) },
        { label: "Time", value: (s) => shiftTimes(s) },
        { label: "Branch", value: (s) => branchName(map, s.branch_id) },
        { label: "Status", value: (s) => s.status },
        { label: "Checked in", value: (s) => (s.checked_in_at ? fmtTime(s.checked_in_at) : "–") },
        { label: "Checked out", value: (s) => (s.checked_out_at ? fmtTime(s.checked_out_at) : "–") },
        { label: "Late minutes", value: (s) => fmtText(s.late_minutes) },
        { label: "Worked minutes", value: (s) => fmtText(s.worked_minutes) },
        {
          label: "Actions",
          value: (s) =>
            h(
              "div",
              { class: "row-actions" },
              canCheckIn(s)
                ? button("Check in", () =>
                    ctx.act(() => post(`/shifts/${s.id}/check-in`), (r) => `Checked in. Late minutes: ${r.late_minutes}.`, () => list.reload()),
                  )
                : null,
              checkedIn(s)
                ? button("Check out", () =>
                    ctx.act(() => post(`/shifts/${s.id}/check-out`), (r) => `Checked out. Worked minutes: ${r.worked_minutes}.`, () => list.reload()),
                  )
                : null,
            ),
        },
      ],
      load: (page) =>
        get("/shifts", { page, page_size: 20, staff_id: me.id, from: from.input.value, to: to.input.value, status: status.input.value }),
    });
    const filters = form({
      fields: [from, to, status],
      submit: "Filter",
      label: "Shift filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    replace(
      ctx.body,
      section(
        "My staff profile",
        definitionList([
          ["Name", me.full_name],
          ["Home branch", branchName(map, me.home_branch_id)],
          ["Employment", `${words(me.employment)}, ${me.weekly_hours} hours a week`],
        ]),
      ),
      h("p", { class: "hint" }, "Check in is possible from 30 minutes before the start of a shift until its end; check out after checking in."),
      filters,
      list.el,
    );
    await list.goTo(1);
  },
};

// ---- LIB-UI-STF-05 ---------------------------------------------------------------

const leaveScreen = {
  id: "stf-05",
  title: "Leave",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    let me = null;
    try {
      me = await get("/staff/me");
    } catch (error) {
      // An admin without a staff profile can still decide on requests.
      if (!(ctx.isAdmin && error.code === "NOT_STAFF")) throw error;
    }
    const staff = ctx.isAdmin ? await loadStaff() : me ? [me] : [];
    const nameOf = new Map(staff.map((s) => [s.id, s.full_name]));
    const balanceBox = h("div", { class: "leave-balance" });
    const decisions = h("div", { class: "leave-decisions" });
    const own = h("div", { class: "leave-own" });

    // ---- own leave ----
    let myList = null;
    let adminList = null;
    const reloadAll = async () => {
      await Promise.all([myList?.reload(), adminList?.reload(), loadBalance()]);
    };

    const cancelRequest = (leave) =>
      ctx.ask({
        text: `Cancel the ${leave.kind} leave from ${leave.from_date} to ${leave.to_date}?`,
        onConfirm: () => ctx.act(() => post(`/leave-requests/${leave.id}/cancel`), "Leave request cancelled.", reloadAll),
      });

    const balanceYear = field({ name: "year", label: "Year", type: "number", value: ctx.today.slice(0, 4), min: 1900, max: 2100 });
    async function loadBalance() {
      if (!me) return;
      const data = await get(`/staff/${me.id}/leave-balance`, { year: String(balanceYear.input.value).trim() });
      replace(
        balanceBox,
        definitionList([
          ["Year", String(data.year)],
          ["Entitled", `${data.entitled} days`],
          ["Used", `${data.used} days`],
          ["Pending", `${data.pending} days`],
          ["Remaining", `${data.remaining} days`],
        ]),
      );
    }

    const leaveColumns = (withStaff, actions) => [
      ...(withStaff ? [{ label: "Staff member", value: (l) => nameOf.get(l.staff_id) || `#${l.staff_id}` }] : []),
      { label: "Kind", value: (l) => l.kind },
      { label: "From", value: (l) => fmtDate(l.from_date) },
      { label: "To", value: (l) => fmtDate(l.to_date) },
      { label: "Working days", value: (l) => String(l.days) },
      { label: "Note", value: (l) => fmtText(l.note) },
      { label: "Status", value: (l) => l.status },
      { label: "Decision note", value: (l) => fmtText(l.decision_note) },
      { label: "Requested", value: (l) => fmtDateTime(l.created_at) },
      { label: "Actions", value: actions },
    ];

    if (me) {
      myList = pagedTable({
        onError: (e) => ctx.fail(e),
        columns: leaveColumns(false, (l) => (l.status === "pending" ? button("Cancel", () => cancelRequest(l)) : "–")),
        load: (page) => get("/leave-requests", { page, page_size: 10, staff_id: me.id }),
      });

      const kind = field({ name: "kind", label: "Kind", options: choices(LEAVE_KINDS) });
      const fromDate = field({ name: "from_date", label: "From", type: "date", value: ctx.today });
      const toDate_ = field({ name: "to_date", label: "To", type: "date", value: ctx.today });
      const note = field({ name: "note", label: "Note", type: "textarea", rows: 2, hint: "Up to 500 characters." });
      const daysLine = h("p", { class: "leave-days", "aria-live": "polite" });
      let daysTicket = 0;
      async function showDays() {
        const a = fromDate.input.value;
        const b = toDate_.input.value;
        const mine = (daysTicket += 1);
        if (!isDate(a) || !isDate(b)) {
          replace(daysLine, "Working days: choose both dates.");
          return;
        }
        if (b < a) {
          replace(daysLine, "Working days: the end date is before the start date.");
          return;
        }
        try {
          const data = await get("/calendar/working-days-between", { start: addDays(a, -1), end: b });
          if (mine === daysTicket) replace(daysLine, `Working days: ${data.working_days}`);
        } catch {
          if (mine === daysTicket) replace(daysLine, "Working days cannot be computed.");
        }
      }
      fromDate.input.addEventListener("change", showDays);
      toDate_.input.addEventListener("change", showDays);
      const request = form({
        fields: [kind, fromDate, toDate_, note],
        submit: "Request",
        label: "Request leave",
        extra: daysLine,
        onSubmit(v) {
          request.fieldErrors({});
          return ctx.act(
            () => post("/leave-requests", { kind: v.kind, from_date: v.from_date, to_date: v.to_date, note: v.note.trim() }),
            (l) => `Leave requested: ${l.days} working days, status ${l.status}.`,
            reloadAll,
            (error) => request.fieldErrors(fieldProblems(error)),
          );
        },
      });
      const balanceForm = form({
        fields: [balanceYear],
        submit: "Show balance",
        label: "Leave balance",
        cls: "filters",
        async onSubmit() {
          ctx.clearMessages();
          try {
            await loadBalance();
          } catch (error) {
            ctx.fail(error);
          }
        },
      });
      replace(
        own,
        section("Request leave", request),
        section("Leave balance", balanceForm, balanceBox),
        section("My leave requests", myList.el),
      );
      showDays();
    } else {
      replace(own, h("p", {}, "You have no staff profile, so you cannot request leave."));
    }

    // ---- admin: decisions ----
    if (ctx.isAdmin) {
      const staffFilter = field({ name: "staff_id", label: "Staff member", options: [anyOption(), ...recordOptions(staff, (s) => s.full_name)] });
      const statusFilter = field({ name: "status", label: "Status", options: choices(LEAVE_STATUSES, { any: "Any" }), value: "pending" });
      const kindFilter = field({ name: "kind", label: "Kind", options: choices(LEAVE_KINDS, { any: "Any" }) });
      const yearFilter = field({ name: "year", label: "Year", type: "number", min: 1900, max: 2100 });

      async function decide(leave, approve) {
        let preview = null;
        if (approve) {
          const shifts = await fetchAll("/shifts", { staff_id: leave.staff_id, from: leave.from_date, to: leave.to_date, status: "planned" });
          preview = shifts.length
            ? h(
                "div",
                { class: "cancelled-shifts" },
                h("p", {}, `These ${shifts.length} planned shifts will be cancelled:`),
                h("ul", {}, shifts.map((s) => h("li", {}, `${dayLabel(s.date)} ${shiftTimes(s)} ${s.staff_name}`))),
              )
            : h("p", {}, "No planned shifts will be cancelled.");
        }
        const note = field({ name: "note", label: "Note", type: "textarea", rows: 2 });
        const who = nameOf.get(leave.staff_id) || `#${leave.staff_id}`;
        ctx.ask({
          text: `${approve ? "Approve" : "Reject"} the ${leave.kind} leave of ${who} from ${leave.from_date} to ${leave.to_date}?`,
          extra: h("div", {}, preview, note),
          onConfirm: () =>
            ctx.act(
              () => post(`/leave-requests/${leave.id}/${approve ? "approve" : "reject"}`, omitNull({ note: text(note.input.value) })),
              (l) => (approve ? `Leave approved. Cancelled shifts: ${l.cancelled_shift_ids.length}.` : "Leave rejected."),
              reloadAll,
            ),
        });
      }

      adminList = pagedTable({
        onError: (e) => ctx.fail(e),
        columns: leaveColumns(true, (l) => {
          const isOwn = me && l.staff_id === me.id;
          const buttons = [];
          if (l.status === "pending" && !isOwn) {
            buttons.push(button("Approve", () => decide(l, true)), button("Reject", () => decide(l, false)));
          }
          if (l.status === "pending" || (l.status === "approved" && l.from_date > ctx.today)) {
            buttons.push(button("Cancel", () => cancelRequest(l)));
          }
          return buttons.length ? h("div", { class: "row-actions" }, buttons) : "–";
        }),
        load: (page) =>
          get("/leave-requests", {
            page,
            page_size: 20,
            staff_id: staffFilter.input.value,
            status: statusFilter.input.value,
            kind: kindFilter.input.value,
            year: yearFilter.input.value.trim(),
          }),
      });
      const filters = form({
        fields: [staffFilter, statusFilter, kindFilter, yearFilter],
        submit: "Filter",
        label: "Leave filters",
        cls: "filters",
        onSubmit() {
          ctx.clearMessages();
          adminList.goTo(1);
        },
      });
      replace(decisions, section("Leave requests of all staff", filters, adminList.el));
    }

    replace(ctx.body, own, decisions);
    await Promise.all([myList?.goTo(1), adminList?.goTo(1), loadBalance()]);
  },
};

// ---- LIB-UI-STF-06 ---------------------------------------------------------------

const staffReportsScreen = {
  id: "stf-06",
  title: "Staff reports",
  module: MODULE,
  roles: ["admin"],
  async render(ctx) {
    const branches = await ctx.branches();
    const preferred = activeBranchIds(branches)[0] || branches[0];

    // staff hours (LIB-STF-43)
    const from = field({ name: "from", label: "From", type: "date", value: `${ctx.today.slice(0, 8)}01` });
    const to = field({ name: "to", label: "To", type: "date", value: ctx.today, hint: "At most 92 days." });
    const branchFilter = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const hours = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Staff member", value: (r) => r.full_name },
        { label: "Planned hours", value: (r) => String(r.planned_hours) },
        { label: "Worked hours", value: (r) => String(r.worked_hours) },
        { label: "Missed shifts", value: (r) => String(r.missed_shifts) },
        { label: "Late minutes", value: (r) => String(r.late_minutes) },
        { label: "Leave days", value: (r) => String(r.leave_days) },
      ],
      load: (page) => get("/reports/staff-hours", { page, page_size: 20, from: from.input.value, to: to.input.value, branch_id: branchFilter.input.value }),
    });
    const hoursForm = form({
      fields: [from, to, branchFilter],
      submit: "Show",
      label: "Staff hours report",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        hours.goTo(1);
      },
    });

    // coverage of one day (LIB-STF-44)
    const dayBranch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches), value: preferred?.id });
    const day = field({ name: "date", label: "Date", type: "date", value: ctx.today });
    const dayBox = h("div", { class: "coverage-day" });
    const dayForm = form({
      fields: [dayBranch, day],
      submit: "Show",
      label: "Branch coverage of a day",
      cls: "filters",
      async onSubmit() {
        ctx.clearMessages();
        try {
          const data = await get("/reports/branch-coverage", { branch_id: dayBranch.input.value, date: day.input.value });
          replace(
            dayBox,
            h("p", {}, data.open ? `Staff needed at every open moment: ${data.min_staff}.` : "The branch is not open on this date."),
            table({
              columns: [
                { label: "Slot", value: (s) => s.start },
                { label: "Staff", value: (s) => String(s.staff) },
                { label: "Covered", value: (s) => (s.ok ? "Yes" : h("strong", { class: "missing" }, "Missing")) },
              ],
              rows: data.slots,
              rowClass: (s) => (s.ok ? undefined : "overdue missing-slot"),
            }),
          );
        } catch (error) {
          ctx.fail(error);
        }
      },
    });

    // understaffed days (LIB-STF-45)
    const rangeBranch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches), value: preferred?.id });
    const rangeFrom = field({ name: "from", label: "From", type: "date", value: `${ctx.today.slice(0, 8)}01` });
    const rangeTo = field({ name: "to", label: "To", type: "date", value: ctx.today, hint: "At most 31 days." });
    const rangeBox = h("div", { class: "coverage-range" });
    const rangeForm = form({
      fields: [rangeBranch, rangeFrom, rangeTo],
      submit: "Show",
      label: "Understaffed days",
      cls: "filters",
      async onSubmit() {
        ctx.clearMessages();
        try {
          const data = await get("/reports/branch-coverage", { branch_id: rangeBranch.input.value, from: rangeFrom.input.value, to: rangeTo.input.value });
          replace(
            rangeBox,
            table({
              columns: [
                { label: "Date", value: (d) => dayLabel(d.date) },
                { label: "Missing slots", value: (d) => String(d.missing_slots) },
              ],
              rows: data.days,
              rowClass: (d) => (d.missing_slots > 0 ? "overdue missing-slot" : undefined),
            }),
          );
        } catch (error) {
          ctx.fail(error);
        }
      },
    });

    replace(
      ctx.body,
      section("Staff hours", hoursForm, hours.el),
      section("Branch coverage of a day", dayForm, dayBox),
      section("Understaffed days", rangeForm, rangeBox),
    );
    await hours.goTo(1);
  },
};

export const staffScreens = [staffScreen, hoursScreen, shiftPlanScreen, myShiftsScreen, leaveScreen, staffReportsScreen];
