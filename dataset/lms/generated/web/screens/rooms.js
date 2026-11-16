// Module 15: study rooms (LIB-UI-ROOM-01 to LIB-UI-ROOM-09).

import { clientError, get, patch, post, queryString, fetchAll } from "../api.js";
import { findMember } from "../context.js";
import { memberPageParts } from "../registry.js";
import {
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
  form,
  h,
  int,
  link,
  omitNull,
  pagedTable,
  replace,
  section,
  table,
  words,
} from "../ui.js";
import { branchMap, branchName, memberLink, withMembers } from "../views.js";

const FEATURES = ["whiteboard", "projector", "power_outlets", "accessible"];
const KINDS = ["individual", "group"];
const STATUSES = ["booked", "checked_in", "completed", "cancelled", "no_show"];

// ---- helpers ---------------------------------------------------------------------

/** A list path with the repeatable query parameter `feature` (LIB-ROOM-03). */
function withFeatures(path, query, features) {
  const base = queryString(query).replace(/^\?/, "");
  const extra = features.map((f) => `feature=${encodeURIComponent(f)}`).join("&");
  const joined = [base, extra].filter(Boolean).join("&");
  return joined ? `${path}?${joined}` : path;
}

const selectedValues = (select) => [...select.selectedOptions].map((o) => o.value);

const featuresField = (spec = {}) =>
  field({
    name: spec.name || "feature",
    label: spec.label || "Features",
    options: choices(FEATURES),
    attrs: { multiple: "", size: "4" },
    hint: "Choose none, one or several; a room needs every chosen feature.",
  });

function timeField(name, label, value) {
  return field({ name, label, type: "time", step: 1800, value });
}

/** Field problems of a 422 answer, plus the field named in `details.field` (for example a duplicate `code`). */
function problems(error) {
  const out = fieldProblems(error);
  const named = error?.details?.field;
  if (typeof named === "string" && !out[named]) out[named] = error.message;
  return out;
}

const hoursText = (room) => `${room.opens_at}–${room.closes_at}`;
const featuresText = (room) => (room.features.length ? room.features.map(words).join(", ") : "–");

const roomLabel = (room, map) => `${branchName(map, room.branch_id)} – ${room.code} ${room.name} (${room.kind}, ${room.capacity})`;

async function roomsById(opts = {}) {
  const rooms = await fetchAll("/rooms", opts);
  return { rooms, byId: new Map(rooms.map((r) => [r.id, r])) };
}

function roomColumns(map, actions) {
  const columns = [
    { label: "Code", value: (r) => link(r.code, `#/room-02/${r.id}`) },
    { label: "Name", value: (r) => r.name },
    { label: "Branch", value: (r) => branchName(map, r.branch_id) },
    { label: "Kind", value: (r) => r.kind },
    { label: "Capacity", value: (r) => String(r.capacity) },
    { label: "Features", value: (r) => featuresText(r) },
    { label: "Hours", value: (r) => hoursText(r) },
    { label: "Active", value: (r) => fmtBool(r.is_active) },
  ];
  if (actions) columns.push({ label: "Actions", value: (r) => actions(r) });
  return columns;
}

const bookingHash = (roomId, date, start, end) => `#/room-04/${roomId}/${date}/${start}/${end}`;

// ---- participants picker ----------------------------------------------------------

/**
 * Members searched by name or member number (LIB-MEM-06 filter `q`). Members cannot call the member list,
 * so for a member the search reports that and the member id can be typed instead.
 */
function participantPicker(ctx, { ids = [] } = {}) {
  const chosen = new Map(ids.map((id) => [id, `Member #${id}`]));
  const list = h("ul", { class: "chosen-participants", "aria-label": "Chosen participants" });
  const note = h("small", { class: "hint" });
  const search = field({ name: "participant_search", label: "Search participants", hint: "By name or member number." });
  const results = field({ name: "participant_candidate", label: "Found members", options: [] });
  const byId = field({ name: "participant_id", label: "Member id", type: "number", min: 1, hint: "Members enter the member id of the participant." });

  function draw() {
    replace(
      list,
      chosen.size ? null : h("li", { class: "none" }, "No participants chosen."),
      [...chosen.entries()].map(([id, label]) =>
        h(
          "li",
          {},
          label,
          " ",
          button("Remove", () => {
            chosen.delete(id);
            draw();
          }),
        ),
      ),
    );
  }

  async function runSearch() {
    const q = search.input.value.trim();
    if (!q) return;
    replace(note, "");
    try {
      const data = await get("/members", { q, page_size: 20 });
      replace(
        results.input,
        data.items.map((m) => h("option", { value: String(m.id) }, `${m.member_no} – ${m.full_name}`)),
      );
      if (!data.items.length) replace(note, "No members found.");
    } catch (error) {
      if (error.code === "FORBIDDEN") replace(note, "Members cannot be searched here; enter the member id below.");
      else ctx.fail(error);
    }
  }
  search.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      runSearch().catch((error) => ctx.fail(error));
    }
  });

  function addFound() {
    const option = results.input.selectedOptions[0];
    if (!option) return;
    chosen.set(Number(option.value), option.textContent);
    draw();
  }

  function addById() {
    const id = int(byId.input.value);
    if (typeof id !== "number" || id < 1) {
      ctx.fail(clientError("VALIDATION_ERROR", "Enter the member id of the participant.", { fields: [{ field: "participant_id", problem: "expected a positive number" }] }));
      return;
    }
    chosen.set(id, `Member #${id}`);
    byId.input.value = "";
    draw();
  }

  const el = h(
    "div",
    { class: "participants-box" },
    h("h3", {}, "Participants"),
    list,
    h("div", { class: "inline-form" }, search, button("Search", runSearch), results, button("Add participant", addFound)),
    ctx.isMember ? h("div", { class: "inline-form" }, byId, button("Add by id", addById)) : null,
    note,
  );
  draw();
  return {
    el,
    ids: () => [...chosen.keys()].sort((a, b) => a - b),
    set(next) {
      chosen.clear();
      for (const id of next) chosen.set(id, `Member #${id}`);
      draw();
    },
  };
}

// ---- LIB-UI-ROOM-01 --------------------------------------------------------------

const roomListScreen = {
  id: "room-01",
  title: "Room list",
  module: "Study rooms",
  roles: ["all"],
  async render(ctx) {
    const map = await branchMap(ctx);
    const branches = await ctx.branches();
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const kind = field({ name: "kind", label: "Kind", options: choices(KINDS, { any: "Any" }) });
    const capacity = field({ name: "min_capacity", label: "Minimum capacity", type: "number", min: 1 });
    const features = featuresField();
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      onRowClick: (r) => ctx.navigate(`#/room-02/${r.id}`),
      columns: roomColumns(map),
      load: (page) =>
        get(
          withFeatures(
            "/rooms",
            { page, page_size: 20, branch_id: branch.input.value, kind: kind.input.value, min_capacity: capacity.input.value.trim() },
            selectedValues(features.input),
          ),
        ),
    });
    const node = form({
      fields: [branch, kind, capacity, features],
      submit: "Show",
      label: "Room filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    replace(ctx.body, node, list.el);
    await list.goTo(1);
  },
};

// ---- LIB-UI-ROOM-02 --------------------------------------------------------------

const availabilityScreen = {
  id: "room-02",
  title: "Availability",
  module: "Study rooms",
  roles: ["all"],
  async render(ctx) {
    const [roomPart, datePart] = ctx.param.split("/");
    const id = /^\d+$/.test(roomPart || "") ? Number(roomPart) : null;
    if (id === null) {
      const map = await branchMap(ctx);
      const { rooms } = await roomsById();
      const choose = field({ name: "room_id", label: "Room", options: rooms.map((r) => ({ value: r.id, label: roomLabel(r, map) })) });
      replace(
        ctx.body,
        form({
          fields: [choose],
          submit: "Open",
          label: "Choose a room",
          onSubmit(v) {
            if (v.room_id) ctx.navigate(`#/room-02/${v.room_id}`);
            else ctx.fail(clientError("VALIDATION_ERROR", "Choose a room.", { fields: [{ field: "room_id", problem: "field required" }] }));
          },
        }),
      );
      return;
    }

    const map = await branchMap(ctx);
    const room = await get(`/rooms/${id}`);
    const date = field({ name: "date", label: "Date", type: "date", value: /^\d{4}-\d\d-\d\d$/.test(datePart || "") ? datePart : ctx.today });
    const gridBox = h("div", { class: "slot-grid-box" });
    const actionBox = h("div", { class: "slot-actions" });
    let slots = [];
    let buttons = [];
    let selected = [];
    let ticket = 0;

    function refresh() {
      buttons.forEach((b, i) => {
        if (!b) return;
        const on = selected.includes(i);
        b.setAttribute("aria-pressed", on ? "true" : "false");
        b.classList.toggle("selected", on);
      });
      if (!selected.length) {
        replace(actionBox, h("p", { class: "hint" }, "Select one or more consecutive free slots to book them."));
        return;
      }
      const start = slots[selected[0]].start;
      const end = slots[selected.at(-1)].end;
      replace(
        actionBox,
        h("p", {}, `Selected: ${start}–${end}`),
        button("Book", () => ctx.navigate(bookingHash(id, date.input.value, start, end))),
      );
    }

    function click(i) {
      if (!selected.length) {
        selected = [i];
      } else {
        const lo = selected[0];
        const hi = selected.at(-1);
        if (i === lo - 1) selected.unshift(i);
        else if (i === hi + 1) selected.push(i);
        else if (i >= lo && i <= hi) {
          if (i === lo && i === hi) selected = [];
          else if (i === hi) selected.pop();
          else if (i === lo) selected.shift();
          else selected = selected.filter((x) => x <= i);
        } else selected = [i];
      }
      refresh();
    }

    async function load() {
      const mine = (ticket += 1);
      const day = date.input.value;
      if (!day) return;
      let data;
      try {
        data = await get(`/rooms/${id}/availability`, { date: day });
      } catch (error) {
        ctx.fail(error);
        return;
      }
      if (mine !== ticket) return;
      selected = [];
      slots = data.slots;
      buttons = [];
      if (!data.open) {
        replace(gridBox, h("p", { class: "closed" }, "closed"));
        replace(actionBox);
        return;
      }
      const grid = h("div", { class: "slot-grid", role: "group", "aria-label": `Slots of ${fmtDate(data.date)}` });
      data.slots.forEach((slot, i) => {
        if (slot.free) {
          const b = button(`${slot.start}–${slot.end} free`, () => click(i), { class: "slot free", "aria-pressed": "false" });
          buttons[i] = b;
          grid.append(b);
        } else {
          grid.append(h("span", { class: "slot booked" }, `${slot.start}–${slot.end} booked`, slot.booking_id ? ` (#${slot.booking_id})` : ""));
        }
      });
      replace(gridBox, grid);
      refresh();
    }
    date.input.addEventListener("change", () => load());

    replace(
      ctx.body,
      section(
        "Room",
        definitionList([
          ["Code", room.code],
          ["Name", room.name],
          ["Branch", branchName(map, room.branch_id)],
          ["Kind", room.kind],
          ["Capacity", String(room.capacity)],
          ["Features", featuresText(room)],
          ["Hours", hoursText(room)],
          ["Active", fmtBool(room.is_active)],
        ]),
        link("Room list", "#/room-01"),
      ),
      section(
        "Slots",
        form({
          fields: [date],
          submit: "Show",
          label: "Choose a date",
          cls: "filters",
          onSubmit() {
            ctx.clearMessages();
            return load();
          },
        }),
        gridBox,
        actionBox,
      ),
    );
    await load();
  },
};

// ---- LIB-UI-ROOM-03 --------------------------------------------------------------

const freeRoomScreen = {
  id: "room-03",
  title: "Find a free room",
  module: "Study rooms",
  roles: ["all"],
  async render(ctx) {
    const map = await branchMap(ctx);
    const branches = await ctx.branches();
    const date = field({ name: "date", label: "Date", type: "date", value: ctx.today });
    const start = timeField("start_time", "Start time", "09:00");
    const end = timeField("end_time", "End time", "10:00");
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const kind = field({ name: "kind", label: "Kind", options: choices(KINDS, { any: "Any" }) });
    const capacity = field({ name: "min_capacity", label: "Minimum capacity", type: "number", min: 1 });
    const features = featuresField();
    // the interval that was searched, so that "Book" opens the booking form with it
    let searched = null;
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: roomColumns(map, (r) =>
        button("Book", () => ctx.navigate(bookingHash(r.id, searched.date, searched.start, searched.end))),
      ),
      load: (page) =>
        get(
          withFeatures(
            "/rooms/free",
            {
              page,
              page_size: 20,
              date: searched.date,
              start_time: searched.start,
              end_time: searched.end,
              branch_id: branch.input.value,
              kind: kind.input.value,
              min_capacity: capacity.input.value.trim(),
            },
            selectedValues(features.input),
          ),
        ),
    });
    const result = h("div", { class: "free-rooms" });
    const node = form({
      fields: [date, start, end, branch, kind, capacity, features],
      submit: "Find rooms",
      label: "Find a free room",
      cls: "filters",
      async onSubmit(v) {
        ctx.clearMessages();
        searched = { date: v.date, start: v.start_time, end: v.end_time };
        replace(result, list.el);
        await list.goTo(1);
      },
    });
    replace(ctx.body, node, result);
  },
};

// ---- LIB-UI-ROOM-04 --------------------------------------------------------------

function bookingFacts(b, room, map) {
  return definitionList([
    ["Booking", String(b.id)],
    ["Room", room ? `${room.code} ${room.name}` : b.room_code],
    ["Branch", branchName(map, b.branch_id)],
    ["Date", fmtDate(b.date)],
    ["Start", b.start_time],
    ["End", b.end_time],
    ["Duration", `${b.duration_minutes} minutes`],
    ["Organizer", `Member #${b.member_id}`],
    ["Participants", b.participant_ids.length ? b.participant_ids.map((id) => `#${id}`).join(", ") : "–"],
    ["Purpose", fmtText(b.purpose)],
    ["Status", words(b.status)],
  ]);
}

const bookingFormScreen = {
  id: "room-04",
  title: "Booking form",
  module: "Study rooms",
  roles: ["all"],
  async render(ctx) {
    const map = await branchMap(ctx);
    const { rooms, byId } = await roomsById({ is_active: "true" });
    const [roomPart, datePart, startPart, endPart] = ctx.param.split("/");
    const wantedRoom = /^\d+$/.test(roomPart || "") ? Number(roomPart) : null;
    const room = field({
      name: "room_id",
      label: "Room",
      options: rooms.map((r) => ({ value: r.id, label: roomLabel(r, map) })),
      value: wantedRoom !== null && byId.has(wantedRoom) ? wantedRoom : undefined,
    });
    const memberNo = ctx.isStaff ? field({ name: "member_no", label: "Organizer member number", hint: "For example M000001." }) : null;
    const date = field({ name: "date", label: "Date", type: "date", value: /^\d{4}-\d\d-\d\d$/.test(datePart || "") ? datePart : ctx.today });
    const start = timeField("start_time", "Start", /^\d\d:\d\d$/.test(startPart || "") ? startPart : "09:00");
    const end = timeField("end_time", "End", /^\d\d:\d\d$/.test(endPart || "") ? endPart : "10:00");
    const purpose = field({ name: "purpose", label: "Purpose", type: "textarea", rows: 2, attrs: { maxlength: "200" } });
    const picker = participantPicker(ctx);
    const result = h("div", { class: "booking-result" });

    function syncKind() {
      const chosen = byId.get(Number(room.input.value));
      picker.el.hidden = !(chosen && chosen.kind === "group");
      if (picker.el.hidden) picker.set([]);
    }
    room.input.addEventListener("change", syncKind);

    const fields = [room, memberNo, date, start, end, picker.el, purpose].filter(Boolean);
    const node = form({
      fields,
      submit: "Book",
      label: "Book a room",
      async onSubmit(v) {
        node.fieldErrors({});
        replace(result);
        const chosen = byId.get(Number(v.room_id));
        const booking = await ctx.act(
          async () => {
            const body = {
              room_id: Number(v.room_id),
              date: v.date,
              start_time: v.start_time,
              end_time: v.end_time,
              participant_ids: chosen && chosen.kind === "group" ? picker.ids() : [],
              purpose: v.purpose.trim(),
            };
            if (ctx.isStaff) body.member_id = (await findMember(v.member_no)).id;
            return post("/room-bookings", body);
          },
          (b) => `Room ${b.room_code} booked for ${fmtDate(b.date)} ${b.start_time}–${b.end_time}.`,
          undefined,
          (error) => node.fieldErrors(problems(error)),
        );
        if (booking) {
          replace(
            result,
            section(
              "Booking",
              bookingFacts(booking, chosen, map),
              ctx.isMember ? link("My room bookings", "#/room-05") : link("Desk view", "#/room-06"),
            ),
          );
        }
      },
    });
    replace(ctx.body, node, result);
    syncKind();
  },
};

// ---- LIB-UI-ROOM-05 --------------------------------------------------------------

const lateWarning =
  "This booking starts today. Cancelling less than 2 hours before the start is a late cancellation: " +
  "no fee, but it counts towards a room ban (3 no-shows or late cancellations within 30 days).";

const myBookingsScreen = {
  id: "room-05",
  title: "My room bookings",
  module: "Study rooms",
  roles: ["member"],
  async render(ctx) {
    const me = ctx.user.member_id;
    const map = await branchMap(ctx);
    const { byId } = await roomsById();
    const info = h("div", { class: "room-info" });
    const editor = h("div", { class: "booking-editor" });

    async function loadInfo() {
      const [summary, bans] = await Promise.all([get(`/members/${me}/summary`), get(`/members/${me}/room-bans`, { page_size: 100 })]);
      const inForce = bans.items.filter((b) => b.in_force);
      replace(
        info,
        section(
          "Room bans and hours",
          definitionList([
            ["Hours this week", `${summary.rooms.hours_this_week} h`],
            ["Upcoming bookings", String(summary.rooms.upcoming_bookings)],
            ["Banned until", summary.rooms.banned_until ? fmtDate(summary.rooms.banned_until) : "–"],
          ]),
          h("h3", {}, "Room bans in force"),
          table({
            columns: [
              { label: "From", value: (b) => fmtDate(b.starts_on) },
              { label: "Until", value: (b) => fmtDate(b.ends_on) },
              { label: "Reason", value: (b) => words(b.reason) },
              { label: "Note", value: (b) => fmtText(b.note) },
            ],
            rows: inForce,
          }),
        ),
      );
    }

    const reloadAll = async () => {
      replace(editor);
      await Promise.all([list.reload(), loadInfo()]);
    };

    function openEditor(b) {
      const room = byId.get(b.room_id);
      const group = room?.kind === "group";
      const picker = participantPicker(ctx, { ids: b.participant_ids });
      const purpose = field({ name: "purpose", label: "Purpose", type: "textarea", rows: 2, value: b.purpose, attrs: { maxlength: "200" } });
      const node = form({
        fields: [group ? picker.el : null, purpose].filter(Boolean),
        submit: "Save",
        label: "Edit participants",
        extra: button("Close", () => replace(editor)),
        async onSubmit(v) {
          const body = {};
          if (group && picker.ids().join(",") !== [...b.participant_ids].sort((x, y) => x - y).join(",")) body.participant_ids = picker.ids();
          if (v.purpose.trim() !== b.purpose) body.purpose = v.purpose.trim();
          if (!Object.keys(body).length) {
            ctx.clearMessages();
            ctx.ok("Nothing to change.");
            return;
          }
          await ctx.act(() => patch(`/room-bookings/${b.id}`, body), "Booking saved.", reloadAll);
        },
      });
      replace(editor, section(`Edit participants of booking ${b.id}`, node));
    }

    function askCancel(b) {
      ctx.ask({
        text: `Cancel the booking of ${b.room_code} on ${fmtDate(b.date)} ${b.start_time}–${b.end_time}?`,
        extra: b.date <= ctx.today ? h("p", { class: "warning" }, lateWarning) : null,
        onConfirm: () =>
          ctx.act(
            () => post(`/room-bookings/${b.id}/cancel`),
            (r) => (r.late_cancellation ? "Booking cancelled. This was a late cancellation." : "Booking cancelled."),
            reloadAll,
          ),
      });
    }

    const status = field({ name: "status", label: "Status", options: choices(STATUSES, { any: "Any" }) });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "ID", value: (b) => String(b.id) },
        { label: "Room", value: (b) => b.room_code },
        { label: "Branch", value: (b) => branchName(map, b.branch_id) },
        { label: "Date", value: (b) => fmtDate(b.date) },
        { label: "Start", value: (b) => b.start_time },
        { label: "End", value: (b) => b.end_time },
        { label: "My role", value: (b) => (b.member_id === me ? "Organizer" : "Participant") },
        { label: "Participants", value: (b) => (b.participant_ids.length ? b.participant_ids.map((id) => (id === me ? "me" : `#${id}`)).join(", ") : "–") },
        { label: "Status", value: (b) => words(b.status) + (b.late_cancellation ? " (late)" : "") },
        { label: "Purpose", value: (b) => fmtText(b.purpose) },
        {
          label: "Actions",
          value: (b) => {
            const organizer = b.member_id === me;
            const upcoming = b.status === "booked" && b.date >= ctx.today;
            const actions = [];
            if (organizer && upcoming && b.date === ctx.today) actions.push(button("Check in", () => ctx.act(() => post(`/room-bookings/${b.id}/check-in`), "Checked in.", reloadAll)));
            if (organizer && b.status === "checked_in") {
              actions.push(
                button("Check out", () =>
                  ctx.act(() => post(`/room-bookings/${b.id}/check-out`), (r) => `Checked out. New end time: ${r.end_time}.`, reloadAll),
                ),
              );
            }
            if (organizer && upcoming) {
              actions.push(button("Edit participants", () => openEditor(b)));
              actions.push(button("Cancel", () => askCancel(b)));
            }
            if (!organizer && upcoming) {
              actions.push(
                button("Leave", () =>
                  ctx.act(
                    () => post(`/room-bookings/${b.id}/leave`),
                    (r) => (r.status === "cancelled" ? "You left the booking. It was cancelled because too few persons remain." : "You left the booking."),
                    reloadAll,
                  ),
                ),
              );
            }
            return h("div", { class: "row-actions" }, actions);
          },
        },
      ],
      load: (page) => get(`/members/${me}/room-bookings`, { page, page_size: 20, status: status.input.value }),
    });
    const filter = form({
      fields: [status],
      submit: "Show",
      label: "Booking filter",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    replace(ctx.body, info, filter, list.el, editor);
    await Promise.all([loadInfo(), list.goTo(1)]);
  },
};

// ---- LIB-UI-ROOM-06 --------------------------------------------------------------

const deskScreen = {
  id: "room-06",
  title: "Desk view",
  module: "Study rooms",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { activeOnly: true }) });
    const reload = () => list.reload();

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      rowClass: (b) => (b.status === "booked" || b.status === "checked_in" ? undefined : "closed-row"),
      columns: [
        { label: "Start", value: (b) => b.start_time },
        { label: "End", value: (b) => b.end_time },
        { label: "Room", value: (b) => b.room_code },
        { label: "Organizer", value: (b) => (b._member ? memberLink(b._member) : `#${b.member_id}`) },
        { label: "Participants", value: (b) => String(b.participant_ids.length) },
        { label: "Status", value: (b) => words(b.status) },
        { label: "Purpose", value: (b) => fmtText(b.purpose) },
        {
          label: "Actions",
          value: (b) => {
            const actions = [];
            if (b.status === "booked") {
              actions.push(button("Check in", () => ctx.act(() => post(`/room-bookings/${b.id}/check-in`), "Checked in.", reload)));
              actions.push(
                button("Cancel", () =>
                  ctx.ask({
                    text: `Cancel the booking of ${b.room_code} at ${b.start_time}–${b.end_time}?`,
                    onConfirm: () => ctx.act(() => post(`/room-bookings/${b.id}/cancel`), "Booking cancelled.", reload),
                  }),
                ),
              );
            }
            if (b.status === "checked_in") {
              actions.push(
                button("Check out", () => ctx.act(() => post(`/room-bookings/${b.id}/check-out`), (r) => `Checked out. New end time: ${r.end_time}.`, reload)),
              );
            }
            return h("div", { class: "row-actions" }, actions);
          },
        },
      ],
      load: async (page) => {
        const data = await get("/room-bookings", { page, page_size: 50, branch_id: branch.input.value, from: ctx.today, to: ctx.today });
        await withMembers(ctx, data.items);
        return data;
      },
    });

    const node = form({
      fields: [branch],
      submit: "Show",
      label: "Choose a branch",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    branch.input.addEventListener("change", () => list.goTo(1));
    const tools = h(
      "div",
      { class: "actions" },
      button("Process", () =>
        ctx.act(
          () => post("/room-bookings/process"),
          (r) => `Processed. No-shows: ${r.no_shows}. Completed: ${r.completed}. Bans: ${r.bans}.`,
          reload,
        ),
      ),
      button("Send reminders", () => ctx.act(() => post("/room-bookings/run-reminders"), (r) => `Reminders sent: ${r.room_reminders}.`)),
    );
    replace(ctx.body, h("p", {}, `Bookings of ${fmtDate(ctx.today)}.`), node, tools, list.el);
    await list.goTo(1);
  },
};

// ---- LIB-UI-ROOM-07 --------------------------------------------------------------

const roomManagementScreen = {
  id: "room-07",
  title: "Room management",
  module: "Study rooms",
  roles: ["admin"],
  desk: true,
  async render(ctx) {
    const map = await branchMap(ctx);
    const branches = await ctx.branches();
    const editor = h("div", { class: "room-editor" });

    // ---- create
    const cBranch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { activeOnly: true }) });
    const cCode = field({ name: "code", label: "Code", hint: "2–10 characters, A–Z and 0–9." });
    const cName = field({ name: "name", label: "Name" });
    const cKind = field({ name: "kind", label: "Kind", options: choices(KINDS) });
    const cCapacity = field({ name: "capacity", label: "Capacity", type: "number", min: 1, hint: "Individual: 1. Group: 3–12. Empty for an individual room means 1." });
    const cMin = field({ name: "min_participants", label: "Minimum participants", type: "number", min: 1, hint: "Individual: 1. Group: 2 up to the capacity." });
    const cFeatures = featuresField({ name: "features" });
    const cOpens = timeField("opens_at", "Opens at", "09:00");
    const cCloses = timeField("closes_at", "Closes at", "18:00");
    const create = form({
      fields: [cBranch, cCode, cName, cKind, cCapacity, cMin, cFeatures, cOpens, cCloses],
      submit: "Create",
      label: "Create room",
      async onSubmit(v) {
        create.fieldErrors({});
        const done = await ctx.act(
          () =>
            post(
              "/rooms",
              omitNull({
                branch_id: Number(v.branch_id),
                code: v.code.trim(),
                name: v.name.trim(),
                kind: v.kind,
                capacity: int(v.capacity),
                min_participants: int(v.min_participants),
                features: selectedValues(cFeatures.input),
                opens_at: v.opens_at,
                closes_at: v.closes_at,
              }),
            ),
          (r) => `Room ${r.code} created.`,
          () => list.reload(),
          (error) => create.fieldErrors(problems(error)),
        );
        if (done) {
          cCode.input.value = "";
          cName.input.value = "";
        }
      },
    });

    // ---- edit
    function openEdit(room) {
      const name = field({ name: "name", label: "Name", value: room.name });
      const capacity = field({ name: "capacity", label: "Capacity", type: "number", min: 1, value: room.capacity });
      const min = field({ name: "min_participants", label: "Minimum participants", type: "number", min: 1, value: room.min_participants });
      const features = featuresField({ name: "features" });
      for (const o of features.input.options) o.selected = room.features.includes(o.value);
      const opens = timeField("opens_at", "Opens at", room.opens_at);
      const closes = timeField("closes_at", "Closes at", room.closes_at);
      const active = field({
        name: "is_active",
        label: "Active",
        options: [{ value: "true", label: "Yes" }, { value: "false", label: "No" }],
        value: String(room.is_active),
      });
      const node = form({
        fields: [name, capacity, min, features, opens, closes, active],
        submit: "Save",
        label: "Edit room",
        extra: button("Close", () => replace(editor)),
        async onSubmit(v) {
          node.fieldErrors({});
          const chosen = selectedValues(features.input);
          const body = omitNull({
            name: v.name.trim() !== room.name ? v.name.trim() : null,
            features: chosen.join(",") !== room.features.join(",") ? chosen : null,
            capacity: int(v.capacity) !== room.capacity ? int(v.capacity) : null,
            min_participants: int(v.min_participants) !== room.min_participants ? int(v.min_participants) : null,
            opens_at: v.opens_at !== room.opens_at ? v.opens_at : null,
            closes_at: v.closes_at !== room.closes_at ? v.closes_at : null,
            is_active: (v.is_active === "true") !== room.is_active ? v.is_active === "true" : null,
          });
          if (!Object.keys(body).length) {
            ctx.clearMessages();
            ctx.ok("Nothing to change.");
            return;
          }
          const save = () =>
            ctx.act(
              () => patch(`/rooms/${room.id}`, body),
              "Room saved.",
              async () => {
                replace(editor);
                await list.reload();
              },
              (error) => node.fieldErrors(problems(error)),
            );
          if (body.is_active === false) {
            ctx.ask({
              text: `Deactivate room ${room.code}? Its future bookings will be cancelled.`,
              onConfirm: save,
            });
          } else {
            await save();
          }
        },
      });
      replace(editor, section(`Edit room ${room.code}`, node));
    }

    const filterBranch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: roomColumns(map, (r) => h("div", { class: "row-actions" }, button("Edit", () => openEdit(r)))),
      load: (page) => get("/rooms", { page, page_size: 20, branch_id: filterBranch.input.value }),
    });
    const filter = form({
      fields: [filterBranch],
      submit: "Show",
      label: "Room filter",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    replace(ctx.body, section("New room", create), section("Rooms", filter, list.el), editor);
    await list.goTo(1);
  },
};

// ---- LIB-UI-ROOM-08 (part of the member page) -------------------------------------

export const roomBansScreen = {
  id: "room-08",
  title: "Room bans",
  module: "Study rooms",
  roles: ["librarian", "admin"],
  part: true,
  async render(ctx) {
    replace(ctx.body, h("p", {}, "The room bans are shown on the member page."), link("Member page", "#/mem-03"));
  },
};

async function roomBansPart(ctx, member) {
  const list = pagedTable({
    onError: (e) => ctx.fail(e),
    columns: [
      { label: "From", value: (b) => fmtDate(b.starts_on) },
      { label: "Until", value: (b) => fmtDate(b.ends_on) },
      { label: "Reason", value: (b) => words(b.reason) },
      { label: "Note", value: (b) => fmtText(b.note) },
      { label: "In force", value: (b) => fmtBool(b.in_force) },
      { label: "Lifted", value: (b) => fmtDateTime(b.lifted_at) },
      {
        label: "Actions",
        value: (b) =>
          ctx.isAdmin && !b.lifted_at && b.ends_on >= ctx.today
            ? button("Lift", () =>
                ctx.ask({
                  text: `Lift the room ban from ${fmtDate(b.starts_on)} to ${fmtDate(b.ends_on)}?`,
                  onConfirm: () => ctx.act(() => post(`/room-bans/${b.id}/lift`), "Room ban lifted.", () => list.reload()),
                }),
              )
            : "–",
      },
    ],
    load: (page) => get(`/members/${member.id}/room-bans`, { page, page_size: 10 }),
  });
  const children = [list.el];
  if (ctx.isAdmin) {
    const starts = field({ name: "starts_on", label: "Starts on", type: "date", value: ctx.today });
    const ends = field({ name: "ends_on", label: "Ends on", type: "date" });
    const note = field({ name: "note", label: "Note", attrs: { maxlength: "500" } });
    const node = form({
      fields: [starts, ends, note],
      submit: "Create",
      label: "Create room ban",
      async onSubmit(v) {
        node.fieldErrors({});
        await ctx.act(
          () => post(`/members/${member.id}/room-bans`, { starts_on: v.starts_on, ends_on: v.ends_on, note: v.note.trim() }),
          "Room ban created.",
          () => list.reload(),
          (error) => node.fieldErrors(problems(error)),
        );
      },
    });
    children.push(h("h3", {}, "New room ban"), node);
  }
  const box = section("Room bans", ...children);
  await list.goTo(1);
  return box;
}

memberPageParts.push({ id: "room-08", render: roomBansPart });

// ---- LIB-UI-ROOM-09 --------------------------------------------------------------

const usageReportScreen = {
  id: "room-09",
  title: "Room usage report",
  module: "Study rooms",
  roles: ["librarian", "admin"],
  async render(ctx) {
    const map = await branchMap(ctx);
    const branches = await ctx.branches();
    const from = field({ name: "from", label: "From", type: "date", value: `${ctx.today.slice(0, 8)}01` });
    const to = field({ name: "to", label: "To", type: "date", value: ctx.today });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "All branches" }) });
    const kind = field({ name: "kind", label: "Kind", options: choices(KINDS, { any: "Any" }) });
    const out = h("div", { class: "report" });
    const list = pagedTable({
      onError: (e) => {
        replace(out);
        ctx.fail(e);
      },
      columns: [
        { label: "Room", value: (r) => link(r.room_code, `#/room-02/${r.room_id}`) },
        { label: "Branch", value: (r) => branchName(map, r.branch_id) },
        { label: "Open hours", value: (r) => r.open_hours },
        { label: "Booked hours", value: (r) => r.booked_hours },
        { label: "Used hours", value: (r) => r.used_hours },
        { label: "No-shows", value: (r) => String(r.no_shows) },
        { label: "Late cancellations", value: (r) => String(r.late_cancellations) },
        { label: "Utilization", value: (r) => `${r.utilization} %` },
      ],
      load: (page) =>
        get("/reports/room-usage", { page, page_size: 50, from: from.input.value, to: to.input.value, branch_id: branch.input.value, kind: kind.input.value }),
    });
    const node = form({
      fields: [from, to, branch, kind],
      submit: "Show",
      label: "Room usage",
      cls: "filters",
      async onSubmit() {
        ctx.clearMessages();
        replace(out, list.el);
        await list.goTo(1);
      },
    });
    replace(ctx.body, node, out);
    node.requestSubmit();
  },
};

export const roomScreens = [
  roomListScreen,
  availabilityScreen,
  freeRoomScreen,
  bookingFormScreen,
  myBookingsScreen,
  deskScreen,
  roomManagementScreen,
  roomBansScreen,
  usageReportScreen,
];
