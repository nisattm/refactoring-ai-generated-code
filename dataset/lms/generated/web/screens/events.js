// Module 20: events (calendar, event page, my events, management, desk, attendance report).

import { fetchAll, get, patch, post } from "../api.js";
import { findMember } from "../context.js";
import {
  branchOptions,
  button,
  choices,
  definitionList,
  field,
  fieldProblems,
  fmtAmount,
  fmtBool,
  fmtDate,
  fmtDateTime,
  fmtText,
  form,
  h,
  int,
  link,
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

const KINDS = ["talk", "workshop", "book_club", "tour"];
const AUDIENCES = ["all", "students", "academics"];
const EVENT_STATUSES = ["draft", "published", "cancelled", "completed"];
const MEMBER_EVENT_STATUSES = ["published", "cancelled", "completed"];
const REGISTRATION_STATUSES = ["registered", "waitlisted", "cancelled", "attended", "no_show"];
const ACTIVE = new Set(["registered", "waitlisted"]);
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// ---- helpers ---------------------------------------------------------------------

function addDays(isoDate, days) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

const pad = (n) => String(n).padStart(2, "0");
const timeRange = (e) => `${e.start_time}–${e.end_time}`;
const eventLink = (e) => link(e.title, `#/evt-02/${e.id}`);
const eventLabel = (e) => `${fmtDate(e.date)} ${e.start_time} ${e.title}`;

/** Responsible staff: names are looked up once per screen (GET /staff/{id} is open to librarians and admins). */
function staffDirectory(ctx) {
  const names = new Map();
  return {
    name(id) {
      if (!names.has(id)) {
        names.set(
          id,
          get(`/staff/${id}`).then(
            (p) => p.full_name,
            () => `#${id}`,
          ),
        );
      }
      return names.get(id);
    },
    async own() {
      try {
        return await get("/staff/me");
      } catch {
        return null;
      }
    },
    async activeProfiles() {
      if (!ctx.isAdmin) return [];
      try {
        return (await fetchAll("/staff", { is_active: "true" })).filter((p) => p.is_active);
      } catch {
        return [];
      }
    },
  };
}

async function withStaffNames(dir, events) {
  await Promise.all(
    events.map(async (e) => {
      e._staff = await dir.name(e.staff_id);
    }),
  );
  return events;
}

function eventColumns(map, { actions, withStaff = false } = {}) {
  const columns = [
    { label: "Date", value: (e) => fmtDate(e.date) },
    { label: "Time", value: (e) => timeRange(e) },
    { label: "Title", value: (e) => eventLink(e) },
    { label: "Kind", value: (e) => words(e.kind) },
    { label: "Branch", value: (e) => branchName(map, e.branch_id) },
    { label: "Free places", value: (e) => `${e.free_places} of ${e.capacity}` },
    { label: "Waiting list", value: (e) => String(e.waitlisted) },
    { label: "Fee", value: (e) => fmtAmount(e.fee) },
    { label: "Status", value: (e) => e.status },
  ];
  if (withStaff) {
    columns.push(
      { label: "Staff", value: (e) => e._staff ?? `#${e.staff_id}` },
      { label: "Staff covered", value: (e) => fmtBool(e.staff_covered) },
    );
  }
  if (actions) columns.push({ label: "Actions", value: (e) => actions(e) });
  return columns;
}

/** Warning for a cancellation that is, or may be, late (LIB-EVT-28, LIB-EVT-29); only the date of "today" is known. */
function lateWarning(event, registration, today) {
  if (registration.status !== "registered") return null;
  const limit = addDays(event.date, -1);
  if (limit < today) {
    return "The free cancellation period is over: this is a late cancellation. A fee for the event stays and has to be paid.";
  }
  if (limit === today) {
    return `Free cancellation ends today at ${event.start_time}. Cancelling later is a late cancellation: a fee for the event stays and has to be paid.`;
  }
  return null;
}

function askCancelRegistration(ctx, event, registration, after) {
  const warning = lateWarning(event, registration, ctx.today);
  ctx.ask({
    text: `Cancel the registration for "${event.title}" on ${fmtDate(event.date)} ${event.start_time}?`,
    extra: warning ? h("p", { class: "late-warning", role: "note" }, h("strong", {}, "Warning: "), warning) : null,
    onConfirm: () =>
      ctx.act(
        () => post(`/event-registrations/${registration.id}/cancel`),
        (r) => (r.late_cancellation ? "Registration cancelled. This was a late cancellation." : "Registration cancelled."),
        after,
      ),
  });
}

function registrationResultText(reg, event) {
  if (reg.status === "waitlisted") return `The event is full: waiting list position ${reg.position}.`;
  const fee = Number(event.fee) > 0 ? ` A fee of ${fmtAmount(event.fee)} was created.` : "";
  return `Registered.${fee}`;
}

// ---- LIB-UI-EVT-01 ---------------------------------------------------------------

function monthGrid(year, month, events) {
  const first = new Date(Date.UTC(year, month - 1, 1));
  const offset = (first.getUTCDay() + 6) % 7;
  const days = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const byDate = new Map();
  for (const e of events) {
    const key = fmtDate(e.date);
    if (!byDate.has(key)) byDate.set(key, []);
    byDate.get(key).push(e);
  }
  const body = h("tbody");
  let row = h("tr");
  for (let i = 0; i < offset; i += 1) row.append(h("td", { class: "month-empty" }));
  for (let day = 1; day <= days; day += 1) {
    const key = `${year}-${pad(month)}-${pad(day)}`;
    const list = byDate.get(key) || [];
    row.append(
      h(
        "td",
        { class: "month-day", "data-date": key },
        h("span", { class: "month-number" }, String(day)),
        list.length
          ? h(
              "ul",
              { class: "month-events" },
              list.map((e) =>
                h(
                  "li",
                  { class: `month-event status-${e.status}` },
                  h("a", { href: `#/evt-02/${e.id}` }, `${e.start_time} ${e.title}`),
                  h("small", {}, ` ${e.status === "published" ? "" : `${e.status}, `}${e.free_places} free, ${e.waitlisted} waiting`),
                ),
              ),
            )
          : null,
      ),
    );
    if ((offset + day) % 7 === 0) {
      body.append(row);
      row = h("tr");
    }
  }
  if (row.children.length) {
    while (row.children.length < 7) row.append(h("td", { class: "month-empty" }));
    body.append(row);
  }
  return h(
    "div",
    { class: "table-wrap" },
    h("table", { class: "month-grid" }, h("thead", {}, h("tr", {}, WEEKDAYS.map((d) => h("th", { scope: "col" }, d)))), body),
  );
}

const eventCalendarScreen = {
  id: "evt-01",
  title: "Event calendar",
  module: "Events",
  roles: ["all"],
  async render(ctx) {
    const map = await branchMap(ctx);
    const branches = await ctx.branches();
    const view = field({
      name: "view",
      label: "View",
      options: [
        { value: "list", label: "List" },
        { value: "month", label: "Month" },
      ],
      value: "list",
    });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const kind = field({ name: "kind", label: "Kind", options: choices(KINDS, { any: "Any" }) });
    const status = field({
      name: "status",
      label: "Status",
      options: choices(ctx.isStaff ? EVENT_STATUSES : MEMBER_EVENT_STATUSES, { any: "Any" }),
      value: ctx.isStaff ? "" : "published",
    });
    const from = field({ name: "from", label: "From", type: "date", value: ctx.today });
    const to = field({ name: "to", label: "To", type: "date" });
    const q = field({ name: "q", label: "Title contains" });

    let year = Number(ctx.today.slice(0, 4));
    let month = Number(ctx.today.slice(5, 7));
    const listBox = h("div", { class: "event-list" });
    const monthBox = h("div", { class: "event-month" });
    const monthTitle = h("h2", { class: "month-title" });
    const grid = h("div", { class: "month-body" });
    let ticket = 0;

    const baseQuery = () => ({
      branch_id: branch.input.value,
      kind: kind.input.value,
      status: status.input.value,
      q: q.input.value.trim(),
    });

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      onRowClick: (e) => ctx.navigate(`#/evt-02/${e.id}`),
      columns: eventColumns(map),
      load: (page) => get("/events", { ...baseQuery(), page, page_size: 20, from: from.input.value, to: to.input.value }),
    });

    async function loadMonth() {
      const mine = (ticket += 1);
      replace(monthTitle, `${MONTHS[month - 1]} ${year}`);
      const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
      try {
        const events = await fetchAll("/events", { ...baseQuery(), from: `${year}-${pad(month)}-01`, to: `${year}-${pad(month)}-${pad(last)}` });
        if (mine !== ticket) return;
        replace(grid, monthGrid(year, month, events));
      } catch (error) {
        if (mine === ticket) ctx.fail(error);
      }
    }

    function step(delta) {
      month += delta;
      if (month < 1) {
        month = 12;
        year -= 1;
      } else if (month > 12) {
        month = 1;
        year += 1;
      }
      ctx.clearMessages();
      return loadMonth();
    }

    replace(
      monthBox,
      h(
        "div",
        { class: "month-nav" },
        button("Previous month", () => step(-1)),
        monthTitle,
        button("Next month", () => step(1)),
      ),
      grid,
    );

    async function show() {
      ctx.clearMessages();
      if (view.input.value === "month") {
        listBox.hidden = true;
        monthBox.hidden = false;
        await loadMonth();
      } else {
        monthBox.hidden = true;
        listBox.hidden = false;
        await list.goTo(1);
      }
    }

    const filters = form({
      fields: [view, branch, kind, status, from, to, q],
      submit: "Filter",
      label: "Event filters",
      cls: "filters",
      onSubmit: show,
    });
    view.input.addEventListener("change", () => show().catch((e) => ctx.fail(e)));
    replace(listBox, list.el);
    replace(
      ctx.body,
      filters,
      h("p", { class: "hint" }, "The month view shows the whole month; the From and To filters apply to the list."),
      listBox,
      monthBox,
    );
    monthBox.hidden = true;
    await show();
  },
};

// ---- LIB-UI-EVT-02 ---------------------------------------------------------------

async function myMemberId(ctx) {
  const me = await get("/members/me");
  return me.id;
}

const eventPageScreen = {
  id: "evt-02",
  title: "Event page",
  module: "Events",
  roles: ["all"],
  async render(ctx) {
    const id = /^\d+$/.test(ctx.param) ? Number(ctx.param) : null;
    if (id === null) {
      const events = await fetchAll("/events", { from: ctx.today });
      const choose = field({
        name: "event_id",
        label: "Event",
        options: events.length ? recordOptions(events, eventLabel) : [{ value: "", label: "No upcoming events" }],
      });
      replace(
        ctx.body,
        form({
          fields: [choose],
          submit: "Open",
          label: "Choose an event",
          onSubmit(v) {
            if (v.event_id) ctx.navigate(`#/evt-02/${v.event_id}`);
          },
        }),
      );
      return;
    }

    const map = await branchMap(ctx);
    const dir = staffDirectory(ctx);
    const memberId = ctx.isMember ? await myMemberId(ctx) : null;
    const info = h("div", { class: "event-info" });
    const actions = h("div", { class: "event-actions" });
    let event = null;

    async function ownRegistration() {
      const regs = await fetchAll(`/members/${memberId}/event-registrations`);
      const mine = regs.filter((r) => r.event_id === id);
      return mine.find((r) => ACTIVE.has(r.status)) || mine[mine.length - 1] || null;
    }

    function registerLabel() {
      return event.free_places > 0 ? "Register" : "Join waiting list";
    }

    function placesInfo() {
      if (event.free_places > 0) return `${event.free_places} of ${event.capacity} places are free.`;
      return `The event is full. ${event.waitlisted} waiting; you would be number ${event.waitlisted + 1} on the waiting list.`;
    }

    async function renderActions() {
      replace(actions);
      if (event.status !== "published") {
        replace(actions, h("p", {}, `This event is ${event.status}; registration is not open.`));
        return;
      }
      if (ctx.isMember) {
        const reg = await ownRegistration();
        if (reg && ACTIVE.has(reg.status)) {
          replace(
            actions,
            h(
              "p",
              { class: "my-registration" },
              reg.status === "registered" ? "You are registered for this event." : `You are on the waiting list at position ${reg.position}.`,
            ),
            button("Cancel", () => askCancelRegistration(ctx, event, reg, reloadAll)),
          );
          return;
        }
        replace(
          actions,
          h("p", {}, placesInfo()),
          button(registerLabel(), () =>
            ctx.act(() => post(`/events/${id}/registrations`, {}), (r) => registrationResultText(r, event), reloadAll),
          ),
        );
        return;
      }
      const memberNo = field({ name: "member_no", label: "Member number", hint: "For example M000001." });
      const node = form({
        fields: [memberNo],
        submit: registerLabel(),
        label: "Register a member",
        async onSubmit(v) {
          ctx.clearMessages();
          let member;
          try {
            member = await findMember(v.member_no);
          } catch (error) {
            ctx.fail(error);
            return;
          }
          await ctx.act(
            () => post(`/events/${id}/registrations`, { member_id: member.id }),
            (r) => registrationResultText(r, event),
            reloadAll,
          );
        },
      });
      replace(
        actions,
        h("p", {}, event.free_places > 0 ? `${event.free_places} of ${event.capacity} places are free.` : `The event is full; ${event.waitlisted} waiting.`),
        node,
        link("Manage this event", `#/evt-04/${id}`),
      );
    }

    async function load() {
      event = await get(`/events/${id}`);
      let room = null;
      if (event.room_id) {
        try {
          room = await get(`/rooms/${event.room_id}`);
        } catch {
          room = null;
        }
      }
      const pairs = [
        ["Title", event.title],
        ["Description", fmtText(event.description)],
        ["Kind", words(event.kind)],
        ["Branch", branchName(map, event.branch_id)],
        ["Room", room ? `${room.code} – ${room.name}` : event.room_id ? `#${event.room_id}` : "–"],
        ["Date", fmtDate(event.date)],
        ["Time", timeRange(event)],
        ["Capacity", String(event.capacity)],
        ["Free places", String(event.free_places)],
        ["Registered", String(event.registered)],
        ["Waiting list", String(event.waitlisted)],
        ["Fee", fmtAmount(event.fee)],
        ["Audience", event.audience],
        ["Status", event.status],
      ];
      if (event.cancel_reason) pairs.push(["Cancel reason", words(event.cancel_reason)]);
      if (ctx.isStaff) {
        pairs.push(["Responsible staff", await dir.name(event.staff_id)], ["Staff covered", fmtBool(event.staff_covered)]);
        if (event.series_id) pairs.push(["Series", String(event.series_id)]);
      }
      replace(info, section("Event", definitionList(pairs)));
      await renderActions();
    }
    const reloadAll = () => load();

    replace(ctx.body, info, section("Registration", actions));
    await load();
  },
};

// ---- LIB-UI-EVT-03 ---------------------------------------------------------------

const myEventsScreen = {
  id: "evt-03",
  title: "My events",
  module: "Events",
  roles: ["member"],
  async render(ctx) {
    const memberId = await myMemberId(ctx);
    const fees = new Map();
    const events = new Map();
    const loadEvent = async (eventId) => {
      if (!events.has(eventId)) events.set(eventId, get(`/events/${eventId}`));
      return events.get(eventId);
    };

    async function prepare(items) {
      const all = await fetchAll(`/members/${memberId}/fees`);
      fees.clear();
      for (const f of all) fees.set(f.id, f);
      await Promise.all(
        items.map(async (r) => {
          try {
            r._event = await loadEvent(r.event_id);
          } catch {
            r._event = null;
          }
        }),
      );
      return items;
    }

    const columns = (withActions) => {
      const list = [
        { label: "Event", value: (r) => link(r.event_title, `#/evt-02/${r.event_id}`) },
        { label: "Date", value: (r) => fmtDate(r.event_date) },
        { label: "Start", value: (r) => r.start_time },
        { label: "Status", value: (r) => words(r.status) },
        { label: "Position", value: (r) => (r.position === null ? "–" : String(r.position)) },
        {
          label: "Fee",
          value: (r) => {
            const fee = r.fee_id ? fees.get(r.fee_id) : null;
            if (fee) return `${fmtAmount(fee.amount)} (${fee.status})`;
            if (r._event && Number(r._event.fee) > 0) return r.status === "waitlisted" ? `${fmtAmount(r._event.fee)} (not charged yet)` : "–";
            return "–";
          },
        },
        { label: "Late cancellation", value: (r) => fmtBool(r.late_cancellation) },
      ];
      if (withActions) {
        list.push({
          label: "Actions",
          value: (r) =>
            ACTIVE.has(r.status) && r._event
              ? button("Cancel", () => askCancelRegistration(ctx, r._event, r, reload))
              : "–",
        });
      }
      return list;
    };

    const upcoming = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: columns(true),
      load: async (page) => {
        const data = await get(`/members/${memberId}/event-registrations`, { page, page_size: 10, from: ctx.today });
        await prepare(data.items);
        return data;
      },
    });
    const past = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: columns(false),
      load: async (page) => {
        const data = await get(`/members/${memberId}/event-registrations`, { page, page_size: 10, to: addDays(ctx.today, -1) });
        await prepare(data.items);
        return data;
      },
    });
    const bansBox = h("div", { class: "event-bans" });

    async function loadBans() {
      const bans = await fetchAll(`/members/${memberId}/event-bans`);
      replace(
        bansBox,
        table({
          columns: [
            { label: "From", value: (b) => fmtDate(b.starts_on) },
            { label: "Until", value: (b) => fmtDate(b.ends_on) },
            { label: "In force", value: (b) => fmtBool(b.starts_on <= ctx.today && ctx.today <= b.ends_on) },
          ],
          rows: bans,
        }),
      );
    }

    async function reload() {
      await Promise.all([upcoming.reload(), past.reload(), loadBans()]);
    }

    replace(
      ctx.body,
      section("Upcoming registrations", upcoming.el),
      section("Past registrations", past.el),
      section("Event bans", bansBox),
    );
    await Promise.all([upcoming.goTo(1), past.goTo(1), loadBans()]);
  },
};

// ---- LIB-UI-EVT-04 ---------------------------------------------------------------

function eventFormFields({ branches, event, ownStaff, profiles, ctx }) {
  const editing = Boolean(event);
  const f = {
    title: field({ name: "title", label: "Title", value: event?.title }),
    description: field({ name: "description", label: "Description", type: "textarea", value: event?.description ?? "" }),
  };
  if (!editing) {
    f.kind = field({ name: "kind", label: "Kind", options: choices(KINDS) });
    f.branch_id = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { activeOnly: true }) });
  }
  f.date = field({ name: "date", label: editing ? "Date" : "Date (first date of a series)", type: "date", value: event ? fmtDate(event.date) : "" });
  f.start_time = field({ name: "start_time", label: "Start time", type: "time", step: "1800", value: event?.start_time, hint: "Minutes 00 or 30; 1–4 hours long." });
  f.end_time = field({ name: "end_time", label: "End time", type: "time", step: "1800", value: event?.end_time });
  f.capacity = field({ name: "capacity", label: "Capacity", type: "number", min: 1, max: 200, value: event?.capacity ?? "" });
  f.fee = field({ name: "fee", label: "Fee", inputmode: "decimal", value: event?.fee ?? "0.00", hint: "0.00 to 200.00 TL." });
  if (!editing) f.audience = field({ name: "audience", label: "Audience", options: choices(AUDIENCES) });
  if (ctx.isAdmin && profiles.length) {
    f.staff_id = field({
      name: "staff_id",
      label: "Responsible staff",
      options: recordOptions(profiles, (p) => p.full_name),
      value: event?.staff_id ?? ownStaff?.id,
    });
  } else {
    f.staff_id = field({
      name: "staff_id",
      label: "Responsible staff (staff profile number)",
      type: "number",
      min: 1,
      value: event?.staff_id ?? ownStaff?.id ?? "",
      hint: ownStaff ? `Your own staff profile number is ${ownStaff.id}.` : undefined,
    });
  }
  f.room_id = field({ name: "room_id", label: "Room (group rooms)", options: [{ value: "", label: "No room" }] });
  if (!editing) {
    f.weeks = field({
      name: "weeks",
      label: "Weeks (series)",
      type: "number",
      min: 2,
      max: 12,
      hint: "Leave empty for one event; 2–12 creates a weekly series starting on the date.",
    });
  }
  return f;
}

const eventManagementScreen = {
  id: "evt-04",
  title: "Event management",
  module: "Events",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const map = await branchMap(ctx);
    const branches = await ctx.branches();
    const dir = staffDirectory(ctx);
    const own = await dir.own();
    const profiles = await dir.activeProfiles();
    const formBox = h("div", { class: "event-form" });
    const resultBox = h("div", { class: "series-result" });
    const regBox = h("div", { class: "event-registrations" });

    // ---- filters and list
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const kind = field({ name: "kind", label: "Kind", options: choices(KINDS, { any: "Any" }) });
    const status = field({ name: "status", label: "Status", options: choices(EVENT_STATUSES, { any: "Any" }) });
    const from = field({ name: "from", label: "From", type: "date", value: ctx.today });
    const to = field({ name: "to", label: "To", type: "date" });
    const seriesId = field({ name: "series_id", label: "Series", type: "number", min: 1 });
    const q = field({ name: "q", label: "Title contains" });

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        ...eventColumns(map, { withStaff: true }),
        { label: "Series", value: (e) => (e.series_id ? String(e.series_id) : "–") },
        {
          label: "Actions",
          value: (e) =>
            h(
              "span",
              { class: "row-actions" },
              e.status === "draft" || e.status === "published" ? button("Edit", () => openForm(e)) : null,
              e.status === "draft" ? button("Publish", () => publish(e)) : null,
              e.status === "draft" || e.status === "published" ? button("Cancel", () => cancelEvent(e)) : null,
              e.series_id && (e.status === "draft" || e.status === "published") ? button("Cancel series", () => cancelSeries(e)) : null,
              button("Registrations", () => openRegistrations(e)),
            ),
        },
      ],
      load: async (page) => {
        const data = await get("/events", {
          page,
          page_size: 20,
          branch_id: branch.input.value,
          kind: kind.input.value,
          status: status.input.value,
          from: from.input.value,
          to: to.input.value,
          series_id: seriesId.input.value.trim(),
          q: q.input.value.trim(),
        });
        await withStaffNames(dir, data.items);
        return data;
      },
    });

    const reload = () => list.reload();

    function publish(e) {
      return ctx.act(() => post(`/events/${e.id}/publish`), (r) => `Event "${r.title}" published.`, reload);
    }

    function cancelEvent(e) {
      ctx.ask({
        text: `Cancel "${e.title}" on ${fmtDate(e.date)}? Registered and waiting members are notified, their registrations are cancelled and open fees are waived.`,
        onConfirm: () => ctx.act(() => post(`/events/${e.id}/cancel`), "Event cancelled.", reload),
      });
    }

    function cancelSeries(e) {
      ctx.ask({
        text: `Cancel all draft and upcoming events of series ${e.series_id}?`,
        onConfirm: () =>
          ctx.act(
            () => post(`/event-series/${e.series_id}/cancel`),
            (r) => `Series cancelled: ${r.cancelled.length} event(s).`,
            reload,
          ),
      });
    }

    // ---- create and change
    function openForm(event = null) {
      ctx.clearMessages();
      replace(resultBox);
      const f = eventFormFields({ branches, event, ownStaff: own, profiles, ctx });
      const node = form({
        fields: Object.values(f),
        submit: event ? "Save" : "Create",
        label: event ? "Change event" : "New event",
        extra: button("Close", () => replace(formBox)),
        async onSubmit(v) {
          node.fieldErrors({});
          const roomId = v.room_id === "" ? null : Number(v.room_id);
          const onError = (error) => node.fieldErrors(fieldProblems(error));
          if (event) {
            const body = {};
            if (v.title.trim() !== event.title) body.title = v.title.trim();
            if (v.description.trim() !== event.description) body.description = v.description.trim();
            if (roomId !== event.room_id) body.room_id = roomId;
            if (v.date !== fmtDate(event.date)) body.date = v.date;
            if (v.start_time !== event.start_time) body.start_time = v.start_time;
            if (v.end_time !== event.end_time) body.end_time = v.end_time;
            if (String(int(v.capacity)) !== String(event.capacity)) body.capacity = int(v.capacity);
            const fee = text(v.fee);
            if (fee !== null && Number(fee) !== Number(event.fee)) body.fee = fee;
            if (String(int(v.staff_id)) !== String(event.staff_id)) body.staff_id = int(v.staff_id);
            await ctx.act(
              () => patch(`/events/${event.id}`, body),
              (r) => `Event saved. Responsible staff covered: ${fmtBool(r.staff_covered)}.`,
              async () => {
                replace(formBox);
                await reload();
              },
              onError,
            );
            return;
          }
          const common = omitNull({
            title: v.title.trim(),
            description: v.description.trim(),
            kind: v.kind,
            branch_id: Number(v.branch_id),
            room_id: roomId,
            start_time: v.start_time,
            end_time: v.end_time,
            capacity: int(v.capacity),
            fee: text(v.fee),
            audience: v.audience,
            staff_id: int(v.staff_id),
          });
          const weeks = text(v.weeks);
          if (weeks !== null) {
            await ctx.act(
              () => post("/event-series", { ...common, first_date: v.date, weeks: int(weeks) }),
              (r) => `Series ${r.series_id} created as drafts: ${r.created.length} event(s), ${r.skipped.length} skipped.`,
              async (r) => {
                replace(
                  resultBox,
                  section(
                    "Series result",
                    h("p", {}, `Created events: ${r.created.join(", ") || "none"}.`),
                    table({
                      caption: "Skipped dates",
                      columns: [
                        { label: "Date", value: (s) => fmtDate(s.date) },
                        { label: "Error code", value: (s) => s.error_code },
                      ],
                      rows: r.skipped,
                    }),
                  ),
                );
                replace(formBox);
                await reload();
              },
              onError,
            );
            return;
          }
          await ctx.act(
            () => post("/events", { ...common, date: v.date }),
            (r) => `Event ${r.id} created as draft. Responsible staff covered: ${fmtBool(r.staff_covered)}.`,
            async () => {
              replace(formBox);
              await reload();
            },
            onError,
          );
        },
      });

      // The room list follows branch, date and times: free group rooms of that branch.
      async function refreshRooms() {
        const branchId = event ? event.branch_id : f.branch_id.input.value;
        const date = f.date.input.value;
        const start = f.start_time.input.value;
        const end = f.end_time.input.value;
        const keep = f.room_id.input.value || (event?.room_id ? String(event.room_id) : "");
        let rooms = [];
        try {
          if (date && start && end && start < end) {
            rooms = await fetchAll("/rooms/free", { date, start_time: start, end_time: end, branch_id: branchId, kind: "group" });
          } else {
            rooms = await fetchAll("/rooms", { branch_id: branchId, kind: "group", is_active: "true" });
          }
        } catch {
          try {
            rooms = await fetchAll("/rooms", { branch_id: branchId, kind: "group", is_active: "true" });
          } catch {
            rooms = [];
          }
        }
        if (event?.room_id && !rooms.some((r) => r.id === event.room_id)) {
          try {
            rooms.push(await get(`/rooms/${event.room_id}`));
          } catch {
            // the current room is simply not offered
          }
        }
        const select = f.room_id.input;
        select.replaceChildren(
          h("option", { value: "" }, "No room"),
          ...rooms.map((r) => h("option", { value: String(r.id) }, `${r.code} – ${r.name} (capacity ${r.capacity})`)),
        );
        select.value = rooms.some((r) => String(r.id) === keep) ? keep : "";
      }
      for (const name of ["branch_id", "date", "start_time", "end_time"]) {
        f[name]?.input.addEventListener("change", () => refreshRooms());
      }

      const heading = event ? `Change event ${event.id}: ${event.title}` : "New event";
      const fixed = event
        ? definitionList([
            ["Kind", words(event.kind)],
            ["Branch", branchName(map, event.branch_id)],
            ["Audience", event.audience],
            ["Status", event.status],
            ["Staff covered", fmtBool(event.staff_covered)],
          ])
        : null;
      replace(formBox, section(heading, fixed, node));
      refreshRooms();
      f.title.input.focus();
    }

    // ---- registrations of one event
    async function openRegistrations(event) {
      const regStatus = field({ name: "status", label: "Registration status", options: choices(REGISTRATION_STATUSES, { any: "Any" }) });
      const regList = pagedTable({
        onError: (e) => ctx.fail(e),
        columns: [
          { label: "Member", value: (r) => (r._member ? link(r._member.member_no, `#/mem-03/${r._member.id}`) : `#${r.member_id}`) },
          { label: "Name", value: (r) => r._member?.full_name ?? "–" },
          { label: "Status", value: (r) => words(r.status) },
          { label: "Position", value: (r) => (r.position === null ? "–" : String(r.position)) },
          { label: "Registered at", value: (r) => fmtDateTime(r.created_at) },
          { label: "Late cancellation", value: (r) => fmtBool(r.late_cancellation) },
          { label: "Fee", value: (r) => fmtText(r.fee_id) },
          {
            label: "Actions",
            value: (r) =>
              ACTIVE.has(r.status)
                ? button("Cancel", () => askCancelRegistration(ctx, event, r, async () => { await regList.reload(); await reload(); }))
                : "–",
          },
        ],
        load: async (page) => {
          const data = await get(`/events/${event.id}/registrations`, { page, page_size: 20, status: regStatus.input.value });
          await Promise.all(
            data.items.map(async (r) => {
              try {
                r._member = await ctx.member(r.member_id);
              } catch {
                r._member = null;
              }
            }),
          );
          return data;
        },
      });
      const filter = form({
        fields: [regStatus],
        submit: "Filter",
        label: "Registration filters",
        cls: "filters",
        onSubmit: () => regList.goTo(1),
      });
      replace(regBox, section(`Registrations of ${event.title} (${fmtDate(event.date)} ${event.start_time})`, filter, regList.el, button("Close", () => replace(regBox))));
      await regList.goTo(1);
      regBox.scrollIntoView?.({ block: "nearest" });
    }

    const filters = form({
      fields: [branch, kind, status, from, to, seriesId, q],
      submit: "Filter",
      label: "Event filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return list.goTo(1);
      },
    });
    replace(ctx.body, h("div", { class: "actions" }, button("New event", () => openForm())), formBox, resultBox, filters, list.el, regBox);
    await list.goTo(1);
    if (/^\d+$/.test(ctx.param)) {
      try {
        await openRegistrations(await get(`/events/${ctx.param}`));
      } catch (error) {
        ctx.fail(error);
      }
    }
  },
};

// ---- LIB-UI-EVT-05 ---------------------------------------------------------------

const eventDeskScreen = {
  id: "evt-05",
  title: "Event desk",
  module: "Events",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const map = await branchMap(ctx);
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "All branches" }) });
    const eventsBox = h("div", { class: "desk-events" });

    async function load() {
      const found = await fetchAll("/events", { from: ctx.today, to: ctx.today, branch_id: branch.input.value });
      const events = found.filter((e) => e.status === "published" || e.status === "completed");
      if (!events.length) {
        replace(
          eventsBox,
          table({
            columns: [
              { label: "Time", value: (e) => timeRange(e) },
              { label: "Title", value: (e) => e.title },
            ],
            rows: [],
          }),
        );
        return;
      }
      const sections = [];
      for (const event of events) {
        const regs = await fetchAll(`/events/${event.id}/registrations`);
        await Promise.all(
          regs.map(async (r) => {
            try {
              r._member = await ctx.member(r.member_id);
            } catch {
              r._member = null;
            }
          }),
        );
        sections.push(
          section(
            `${timeRange(event)} ${event.title}`,
            definitionList([
              ["Branch", branchName(map, event.branch_id)],
              ["Status", event.status],
              ["Free places", `${event.free_places} of ${event.capacity}`],
              ["Waiting list", String(event.waitlisted)],
            ]),
            table({
              columns: [
                { label: "Member", value: (r) => (r._member ? link(r._member.member_no, `#/mem-03/${r._member.id}`) : `#${r.member_id}`) },
                { label: "Name", value: (r) => r._member?.full_name ?? "–" },
                { label: "Status", value: (r) => words(r.status) },
                { label: "Position", value: (r) => (r.position === null ? "–" : String(r.position)) },
                {
                  label: "Actions",
                  value: (r) =>
                    r.status === "registered"
                      ? button("Check in", () =>
                          ctx.act(
                            () => post(`/event-registrations/${r.id}/check-in`),
                            `${r._member?.full_name ?? "Member"} checked in.`,
                            load,
                          ),
                        )
                      : "–",
                },
              ],
              rows: regs,
            }),
          ),
        );
      }
      replace(eventsBox, sections);
    }

    const filter = form({
      fields: [branch],
      submit: "Show",
      label: "Desk branch",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return load();
      },
    });
    const process = button("Process", () =>
      ctx.act(
        () => post("/events/process"),
        (r) => `Processed. Completed events: ${r.completed_events}. No-shows: ${r.no_shows}. Bans: ${r.bans}. Reminders: ${r.reminders}.`,
        load,
      ),
    );
    replace(ctx.body, filter, h("div", { class: "actions" }, process), eventsBox);
    await load();
  },
};

// ---- LIB-UI-EVT-06 ---------------------------------------------------------------

const attendanceReportScreen = {
  id: "evt-06",
  title: "Attendance report",
  module: "Events",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const from = field({ name: "from", label: "From", type: "date", value: addDays(ctx.today, -29) });
    const to = field({ name: "to", label: "To", type: "date", value: ctx.today });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "All branches" }) });
    const kind = field({ name: "kind", label: "Kind", options: choices(KINDS, { any: "Any" }) });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Date", value: (r) => fmtDate(r.date) },
        { label: "Title", value: (r) => link(r.title, `#/evt-02/${r.event_id}`) },
        { label: "Kind", value: (r) => words(r.kind) },
        { label: "Status", value: (r) => r.status },
        { label: "Capacity", value: (r) => String(r.capacity) },
        { label: "Registered", value: (r) => String(r.registered) },
        { label: "Attended", value: (r) => String(r.attended) },
        { label: "No-shows", value: (r) => String(r.no_shows) },
        { label: "Late cancellations", value: (r) => String(r.late_cancellations) },
        { label: "Fees charged", value: (r) => fmtAmount(r.fees_charged) },
      ],
      load: (page) =>
        get("/reports/event-attendance", {
          page,
          page_size: 20,
          from: from.input.value,
          to: to.input.value,
          branch_id: branch.input.value,
          kind: kind.input.value,
        }),
    });
    const node = form({
      fields: [from, to, branch, kind],
      submit: "Show",
      label: "Attendance report",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return list.goTo(1);
      },
    });
    replace(ctx.body, node, list.el);
    await list.goTo(1);
  },
};

export const eventScreens = [
  eventCalendarScreen,
  eventPageScreen,
  myEventsScreen,
  eventManagementScreen,
  eventDeskScreen,
  attendanceReportScreen,
];
