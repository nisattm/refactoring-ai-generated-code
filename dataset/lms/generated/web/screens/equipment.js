// Module 16: equipment loans (WEB_INTERFACE.md section 3.2).

import { ApiError, clientError, fetchAll, get, patch, post } from "../api.js";
import { findMember } from "../context.js";
import { memberPageParts } from "../registry.js";
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
  fmtTime,
  form,
  h,
  omitNull,
  pagedTable,
  recordOptions,
  replace,
  section,
  words,
} from "../ui.js";
import { branchMap, branchName, memberLink, memberPicker, withMembers } from "../views.js";

const MODULE = "Equipment loans";
// Library time is fixed at UTC+03:00 (LIB-COM-01); request date-times carry that offset.
const OFFSET = "+03:00";

// ---- shared helpers ----------------------------------------------------------------

const loadTypes = () => fetchAll("/equipment-types");

const typeLabel = (type) => `${type.code} – ${type.name}${type.is_active ? "" : " (inactive)"}`;
const typeOptions = (types, { any } = {}) => recordOptions(types, typeLabel, { any });
const typeMapOf = (types) => new Map(types.map((t) => [t.id, t]));
const typeName = (map, id) => (map.get(id) ? map.get(id).name : `#${id}`);
const periodText = (type) => `${type.period} ${type.period_unit === "hours" ? "hours" : "working days"}`;

const LOAN_STATUSES = ["open", "returned", "lost"];
const ITEM_STATUSES = ["available", "on_loan", "in_repair", "lost", "retired"];
const CONDITIONS = ["good", "damaged"];
const YES_NO = [
  { value: "true", label: "Yes" },
  { value: "false", label: "No" },
];

function addDays(isoDate, days) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

const toStamp = (date, time) => `${date}T${time}:00${OFFSET}`;

/** DESK_CLOSED names the next opening time (LIB-EQ-13). */
function withOpeningTime(error) {
  if (error instanceof ApiError && error.code === "DESK_CLOSED" && error.details?.opens_at) {
    return new ApiError(
      error.status,
      error.code,
      `${error.message} The desk opens at ${fmtDateTime(error.details.opens_at)}.`,
      error.details,
    );
  }
  return error;
}

async function deskCall(run) {
  try {
    return await run();
  } catch (error) {
    throw withOpeningTime(error);
  }
}

/** The `ends_at` a reservation (or loan) starting at `date time` gets (LIB-EQ-15). */
async function endsAtOf(type, date, time) {
  if (type.period_unit === "hours") {
    const [hh, mm] = time.split(":").map(Number);
    const minutes = Math.min(hh * 60 + mm + type.period * 60, 20 * 60);
    const pad = (n) => String(n).padStart(2, "0");
    return `${date} ${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;
  }
  const result = await get("/calendar/add-working-days", { date, days: type.period });
  return `${result.date} 17:00`;
}

/** Half-hour grid of LIB-EQ-33; a day without slots is shown as "closed". */
function slotGrid(data, { onPick, selected } = {}) {
  const wrap = h("div", { class: "slot-grid-wrap" }, h("p", {}, `Capacity: ${data.capacity}`));
  if (!data.slots.length) {
    wrap.append(h("p", { class: "slot-closed" }, "closed"));
    return wrap;
  }
  const grid = h("div", { class: "slot-grid", role: "group", "aria-label": "Start times" });
  for (const slot of data.slots) {
    const free = slot.free > 0;
    const node = button(`${slot.start} (${slot.free} free)`, () => onPick?.(slot), {
      class: `slot ${free ? "slot-free" : "slot-full"}`,
      disabled: !free || !onPick,
      "aria-pressed": selected === slot.start ? "true" : "false",
    });
    grid.append(node);
  }
  wrap.append(grid);
  return wrap;
}

async function ownMember() {
  return get("/members/me");
}

async function findItem(assetTag) {
  const wanted = String(assetTag ?? "").trim();
  if (!wanted) {
    throw clientError("VALIDATION_ERROR", "Enter an asset tag.", { fields: [{ field: "asset_tag", problem: "field required" }] });
  }
  const data = await get("/equipment-items", { q: wanted, page_size: 100 });
  const found = data.items.find((i) => i.asset_tag.toLowerCase() === wanted.toLowerCase());
  if (!found) throw clientError("NOT_FOUND", `No equipment item with asset tag ${wanted}.`, { field: "asset_tag", value: wanted });
  return found;
}

async function openLoanOfItem(item) {
  const loans = await fetchAll("/equipment-loans", { status: "open", type_id: item.type_id, branch_id: item.branch_id });
  const loan = loans.find((l) => l.item_id === item.id);
  if (!loan) throw clientError("LOAN_NOT_OPEN", `Item ${item.asset_tag} has no open loan.`, { asset_tag: item.asset_tag });
  return loan;
}

function loanColumns({ types, map, withMember = false, actions }) {
  const columns = [{ label: "ID", value: (l) => String(l.id) }];
  if (withMember) columns.push({ label: "Member", value: (l) => (l._member ? memberLink(l._member) : `#${l.member_id}`) });
  columns.push(
    { label: "Type", value: (l) => typeName(types, l.type_id) },
    { label: "Asset tag", value: (l) => l.asset_tag },
    { label: "Branch", value: (l) => branchName(map, l.branch_id) },
    { label: "Loaned at", value: (l) => fmtDateTime(l.loaned_at) },
    { label: "Due at", value: (l) => fmtDateTime(l.due_at) },
    { label: "Status", value: (l) => l.status },
    { label: "Overdue", value: (l) => fmtBool(l.overdue) },
    { label: "Extended", value: (l) => fmtBool(l.extended) },
    { label: "Late fee", value: (l) => fmtAmount(l.accrued_late_fee) },
    { label: "Returned at", value: (l) => fmtDateTime(l.returned_at) },
  );
  if (actions) columns.push({ label: "Actions", value: (l) => actions(l) });
  return columns;
}

function reservationColumns({ types, map, withMember = false, actions }) {
  const columns = [{ label: "ID", value: (r) => String(r.id) }];
  if (withMember) columns.push({ label: "Member", value: (r) => (r._member ? memberLink(r._member) : `#${r.member_id}`) });
  columns.push(
    { label: "Type", value: (r) => typeName(types, r.type_id) },
    { label: "Branch", value: (r) => branchName(map, r.branch_id) },
    { label: "Starts at", value: (r) => fmtDateTime(r.starts_at) },
    { label: "Ends at", value: (r) => fmtDateTime(r.ends_at) },
    { label: "Status", value: (r) => r.status },
    { label: "Reason", value: (r) => (r.cancel_reason ? words(r.cancel_reason) : "–") },
  );
  if (actions) columns.push({ label: "Actions", value: (r) => actions(r) });
  return columns;
}

const trainingColumns = (types, today) => [
  { label: "Type", value: (t) => typeName(types, t.type_id) },
  { label: "Completed on", value: (t) => fmtDate(t.completed_on) },
  { label: "Valid until", value: (t) => fmtDate(t.valid_until) },
  { label: "Valid today", value: (t) => fmtBool(t.completed_on <= today && today <= t.valid_until) },
];

// ---- LIB-UI-EQ-01 ------------------------------------------------------------------

const catalogScreen = {
  id: "eq-01",
  title: "Equipment catalog",
  module: MODULE,
  roles: ["all"],
  async render(ctx) {
    const [types, branches] = await Promise.all([loadTypes(), ctx.branches()]);
    const gridBox = h("div", { class: "availability" });

    const type = field({ name: "type_id", label: "Equipment type", options: typeOptions(types) });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { activeOnly: true }) });
    const date = field({ name: "date", label: "Date", type: "date", value: ctx.today });

    async function showGrid() {
      ctx.clearMessages();
      const typeId = type.input.value;
      if (!typeId || !branch.input.value || !date.input.value) {
        replace(gridBox);
        return;
      }
      try {
        const data = await get(`/equipment-types/${typeId}/availability`, { branch_id: branch.input.value, date: date.input.value });
        const chosen = types.find((t) => String(t.id) === typeId);
        replace(
          gridBox,
          section(
            `Availability of ${chosen ? chosen.name : "type"} on ${fmtDate(data.date)}`,
            slotGrid(data, {
              onPick: (slot) => ctx.navigate(`#/eq-02/${data.type_id}/${data.branch_id}/${data.date}/${slot.start}`),
            }),
          ),
        );
      } catch (error) {
        replace(gridBox);
        ctx.fail(error);
      }
    }

    const picker = form({
      fields: [type, branch, date],
      submit: "Show availability",
      label: "Availability",
      cls: "filters",
      onSubmit: showGrid,
    });

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      onRowClick: (t) => {
        type.input.value = String(t.id);
        return showGrid();
      },
      columns: [
        { label: "Code", value: (t) => t.code },
        { label: "Name", value: (t) => t.name },
        { label: "Loan period", value: periodText },
        { label: "Hourly late fee", value: (t) => fmtAmount(t.hourly_late_fee) },
        { label: "Training required", value: (t) => fmtBool(t.requires_training) },
        { label: "Max open per member", value: (t) => String(t.max_open_per_member) },
        { label: "Active", value: (t) => fmtBool(t.is_active) },
        { label: "Items total", value: (t) => String(t.items_total) },
        { label: "Items available", value: (t) => String(t.items_available) },
        {
          label: "Actions",
          value: (t) =>
            button("Select", () => {
              type.input.value = String(t.id);
              return showGrid();
            }),
        },
      ],
      load: (page) => get("/equipment-types", { page, page_size: 20 }),
    });

    replace(ctx.body, section("Equipment types", list.el), section("Availability", picker, gridBox));
    await list.goTo(1);
  },
};

// ---- LIB-UI-EQ-02 ------------------------------------------------------------------

const reserveScreen = {
  id: "eq-02",
  title: "Reserve equipment",
  module: MODULE,
  roles: ["member", "librarian", "admin"],
  async render(ctx) {
    const [types, branches] = await Promise.all([loadTypes(), ctx.branches()]);
    const activeTypes = types.filter((t) => t.is_active);
    // route parameter: <type_id>/<branch_id>/<date>/<HH:MM> (from the grid of the equipment catalog)
    const [pType, pBranch, pDate, pTime] = ctx.param ? ctx.param.split("/") : [];

    const memberNo = ctx.isStaff ? field({ name: "member_no", label: "Member number", hint: "For example M000001." }) : null;
    const type = field({ name: "type_id", label: "Equipment type", options: typeOptions(activeTypes), value: pType });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { activeOnly: true }), value: pBranch });
    const date = field({ name: "date", label: "Date", type: "date", value: pDate || ctx.today });
    const starts = field({ name: "starts_at", label: "Start", readonly: true, hint: "Pick a free time from the grid." });
    const gridBox = h("div", { class: "availability" });
    const endsLine = h("p", { class: "ends-line" });
    const offer = h("div", { class: "offer" });
    const result = h("div", { class: "reserve-result" });
    let selected = "";
    let ticket = 0;

    async function showEnds() {
      const mine = (ticket += 1);
      const chosen = types.find((t) => String(t.id) === type.input.value);
      if (!selected || !chosen) {
        replace(endsLine);
        return;
      }
      try {
        const ends = await endsAtOf(chosen, date.input.value, selected);
        if (mine === ticket) replace(endsLine, "Ends at: ", h("strong", {}, ends));
      } catch (error) {
        if (mine === ticket) ctx.fail(error);
      }
    }

    function pick(time) {
      selected = time;
      starts.input.value = time ? `${date.input.value} ${time}` : "";
      showEnds();
    }

    async function showGrid() {
      if (!type.input.value || !branch.input.value || !date.input.value) {
        replace(gridBox);
        return;
      }
      try {
        const data = await get(`/equipment-types/${type.input.value}/availability`, {
          branch_id: branch.input.value,
          date: date.input.value,
        });
        replace(
          gridBox,
          slotGrid(data, {
            selected,
            onPick: (slot) => {
              pick(slot.start);
              showGrid();
            },
          }),
        );
      } catch (error) {
        replace(gridBox);
        ctx.fail(error);
      }
    }

    function changed() {
      pick("");
      replace(offer);
      return showGrid();
    }
    for (const f of [type, branch, date]) f.input.addEventListener("change", () => changed());

    const node = form({
      fields: [memberNo, type, branch, date, starts].filter(Boolean),
      submit: "Reserve",
      label: "Reserve equipment",
      async onSubmit(v) {
        replace(offer);
        replace(result);
        if (!selected) {
          ctx.fail(clientError("VALIDATION_ERROR", "Pick a start time from the grid.", { fields: [{ field: "starts_at", problem: "field required" }] }));
          return;
        }
        const done = await ctx.act(
          async () => {
            const body = { type_id: Number(v.type_id), branch_id: Number(v.branch_id), starts_at: toStamp(date.input.value, selected) };
            if (ctx.isStaff) body.member_id = (await findMember(v.member_no)).id;
            return deskCall(() => post("/equipment-reservations", body));
          },
          (r) => `Reservation ${r.id} booked: ${fmtDateTime(r.starts_at)} to ${fmtDateTime(r.ends_at)}.`,
          showGrid,
          (error) => {
            const next = error.details?.next_free_at;
            if (error.code === "NO_EQUIPMENT_AVAILABLE" && next) {
              replace(
                offer,
                button(`Use next free time: ${fmtDateTime(next)}`, () => {
                  date.input.value = fmtDate(next);
                  selected = "";
                  pick(fmtTime(next));
                  return showGrid();
                }),
              );
            }
          },
        );
        if (done) {
          replace(
            result,
            definitionList([
              ["Reservation", String(done.id)],
              ["Starts at", fmtDateTime(done.starts_at)],
              ["Ends at", fmtDateTime(done.ends_at)],
              ["Status", done.status],
            ]),
          );
        }
      },
    });
    node.insertBefore(endsLine, node.querySelector(".actions"));
    node.insertBefore(gridBox, starts);
    replace(ctx.body, section("New reservation", node, offer, result));

    if (pTime && pDate) {
      selected = pTime;
      starts.input.value = `${pDate} ${pTime}`;
      await showEnds();
    }
    await showGrid();
  },
};

// ---- LIB-UI-EQ-03 ------------------------------------------------------------------

const myEquipmentScreen = {
  id: "eq-03",
  title: "My equipment",
  module: MODULE,
  roles: ["member"],
  async render(ctx) {
    const [member, typeList, map] = await Promise.all([ownMember(), loadTypes(), branchMap(ctx)]);
    const types = typeMapOf(typeList);
    const base = `/members/${member.id}`;
    const reloadAll = () => Promise.all([loans.reload(), reservations.reload(), trainings.reload()]);

    const loans = pagedTable({
      onError: (e) => ctx.fail(e),
      rowClass: (l) => (l.overdue ? "overdue" : undefined),
      columns: loanColumns({
        types,
        map,
        actions: (l) =>
          l.status === "open"
            ? button("Extend", () =>
                ctx.act(
                  () => post(`/equipment-loans/${l.id}/extend`),
                  (r) => `Loan extended. New due time: ${fmtDateTime(r.due_at)}.`,
                  reloadAll,
                ),
              )
            : "–",
      }),
      load: (page) => get(`${base}/equipment-loans`, { page, page_size: 10 }),
    });

    const reservations = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: reservationColumns({
        types,
        map,
        actions: (r) =>
          button("Cancel", () =>
            ctx.ask({
              text: `Cancel the reservation of ${typeName(types, r.type_id)} on ${fmtDateTime(r.starts_at)}?`,
              onConfirm: () => ctx.act(() => post(`/equipment-reservations/${r.id}/cancel`), "Reservation cancelled.", reloadAll),
            }),
          ),
      }),
      load: (page) => get(`${base}/equipment-reservations`, { status: "booked", page, page_size: 10 }),
    });

    const trainings = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: trainingColumns(types, ctx.today),
      load: (page) => get(`${base}/equipment-trainings`, { page, page_size: 10 }),
    });

    replace(
      ctx.body,
      section("Loans", loans.el),
      section("Booked reservations", reservations.el),
      section("Trainings", trainings.el),
    );
    await Promise.all([loans.goTo(1), reservations.goTo(1), trainings.goTo(1)]);
  },
};

// ---- LIB-UI-EQ-04 ------------------------------------------------------------------

const deskScreen = {
  id: "eq-04",
  title: "Equipment desk",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const [typeList, branches, map] = await Promise.all([loadTypes(), ctx.branches(), branchMap(ctx)]);
    const types = typeMapOf(typeList);
    let member = null;
    let memberLoans = null;
    let memberReservations = null;

    const memberBox = h("div", { class: "desk-member" });
    const returnResult = h("div", { class: "return-result" });
    const lendResult = h("div", { class: "lend-result" });

    const reloadAll = () =>
      Promise.all([memberLoans?.reload(), memberReservations?.reload(), todayList.reload()].filter(Boolean));

    // return form (also filled by the row action "Return")
    const tag = field({ name: "asset_tag", label: "Asset tag" });
    const condition = field({ name: "condition", label: "Condition", options: choices(CONDITIONS), value: "good" });
    const damage = field({ name: "damage_fee", label: "Damage fee", inputmode: "decimal", hint: "Only for a damaged item." });
    const returnForm = form({
      fields: [tag, condition, damage],
      submit: "Return",
      label: "Return",
      async onSubmit(v) {
        replace(returnResult);
        const loan = await ctx.act(
          async () => {
            const item = await findItem(v.asset_tag);
            const open = await openLoanOfItem(item);
            const body = { condition: v.condition };
            if (v.condition === "damaged" && v.damage_fee.trim() !== "") body.damage_fee = v.damage_fee.trim();
            return post(`/equipment-loans/${open.id}/return`, body);
          },
          (l) => `Returned ${l.asset_tag}. Late hours: ${l.late_hours ?? 0}.`,
          reloadAll,
        );
        if (loan) {
          replace(
            returnResult,
            definitionList([
              ["Asset tag", loan.asset_tag],
              ["Condition", fmtText(loan.return_condition)],
              ["Late hours", String(loan.late_hours ?? 0)],
              ["Returned at", fmtDateTime(loan.returned_at)],
            ]),
          );
          tag.input.value = "";
          damage.input.value = "";
          condition.input.value = "good";
        }
      },
    });

    // today's reservations of a chosen branch
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { activeOnly: true }) });
    const collect = (r) =>
      ctx.act(
        () => deskCall(() => post("/equipment-loans", { member_id: r.member_id, reservation_id: r.id })),
        (l) => `Reservation collected. Loan created for ${l.asset_tag}, due ${fmtDateTime(l.due_at)}.`,
        reloadAll,
      );
    const cancelReservation = (r) =>
      ctx.ask({
        text: `Cancel the reservation of ${typeName(types, r.type_id)} on ${fmtDateTime(r.starts_at)}?`,
        onConfirm: () => ctx.act(() => post(`/equipment-reservations/${r.id}/cancel`), "Reservation cancelled.", reloadAll),
      });
    const reservationActions = (r) =>
      r.status === "booked"
        ? h("span", { class: "row-actions" }, button("Collect", () => collect(r)), button("Cancel", () => cancelReservation(r)))
        : "–";

    const todayList = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: reservationColumns({ types, map, withMember: true, actions: reservationActions }),
      load: async (page) => {
        if (!branch.input.value) return { items: [], page: 1, page_size: 20, total: 0 };
        const data = await get("/equipment-reservations", {
          branch_id: branch.input.value,
          from: ctx.today,
          to: ctx.today,
          page,
          page_size: 20,
        });
        await withMembers(ctx, data.items);
        return data;
      },
    });
    branch.input.addEventListener("change", () => todayList.goTo(1));

    function showMember() {
      const tagField = field({ name: "asset_tag", label: "Asset tag", id: "lend-asset-tag" });
      const lend = form({
        fields: [tagField],
        submit: "Lend",
        label: "Lend",
        async onSubmit(v) {
          replace(lendResult);
          const loan = await ctx.act(
            async () => {
              const item = await findItem(v.asset_tag);
              return deskCall(() => post("/equipment-loans", { member_id: member.id, item_id: item.id }));
            },
            (l) => `Loan created for ${l.asset_tag}. Due at ${fmtDateTime(l.due_at)}.`,
            reloadAll,
          );
          if (loan) {
            replace(lendResult, definitionList([["Asset tag", loan.asset_tag], ["Due at", fmtDateTime(loan.due_at)]]));
            tagField.input.value = "";
          }
        },
      });

      memberLoans = pagedTable({
        onError: (e) => ctx.fail(e),
        rowClass: (l) => (l.overdue ? "overdue" : undefined),
        columns: loanColumns({
          types,
          map,
          actions: (l) =>
            h(
              "span",
              { class: "row-actions" },
              button("Return", () => {
                tag.input.value = l.asset_tag;
                tag.input.focus();
              }),
              button("Report lost", () =>
                ctx.ask({
                  text: `Report ${l.asset_tag} as lost? The member is charged the item value.`,
                  onConfirm: () => ctx.act(() => post(`/equipment-loans/${l.id}/report-lost`), `${l.asset_tag} reported lost.`, reloadAll),
                }),
              ),
            ),
        }),
        load: (page) => get(`/members/${member.id}/equipment-loans`, { status: "open", page, page_size: 10 }),
      });
      memberReservations = pagedTable({
        onError: (e) => ctx.fail(e),
        columns: reservationColumns({ types, map, actions: reservationActions }),
        load: (page) => get(`/members/${member.id}/equipment-reservations`, { status: "booked", page, page_size: 10 }),
      });
      replace(
        memberBox,
        section(
          `Member ${member.member_no}`,
          definitionList([
            ["Name", member.full_name],
            ["Member page", h("a", { href: `#/mem-03/${member.id}` }, member.member_no)],
            ["Type", member.membership_type],
            ["Status", member.status],
          ]),
        ),
        section("Lend by asset tag", lend, lendResult),
        section("Open loans", memberLoans.el),
        section("Booked reservations", memberReservations.el),
      );
      return Promise.all([memberLoans.goTo(1), memberReservations.goTo(1)]);
    }

    const picker = memberPicker(ctx, {
      submit: "Find member",
      async onPick(m) {
        member = m;
        replace(lendResult);
        await showMember();
      },
    });

    const processBox = h("div", { class: "process-box" });
    const processButton = button("Process", async () => {
      replace(processBox);
      await ctx.act(
        () => post("/equipment/process"),
        (r) => `Expired reservations: ${r.expired_reservations}. Overdue notices: ${r.overdue_notices}.`,
        reloadAll,
      );
    });

    replace(
      ctx.body,
      section("Find a member", picker),
      memberBox,
      section("Return", returnForm, returnResult),
      section("Today's reservations", h("div", { class: "filters" }, branch), todayList.el),
      section("Processing", h("p", {}, "Expire reservations that were not collected and send overdue notices."), processButton, processBox),
    );
    await todayList.goTo(1);
  },
};

// ---- LIB-UI-EQ-05 ------------------------------------------------------------------

const typesItemsScreen = {
  id: "eq-05",
  title: "Types and items",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    async function show() {
      const [types, branches, map] = await Promise.all([loadTypes(), ctx.branches(), branchMap(ctx)]);
      const typeMap = typeMapOf(types);
      const editor = h("div", { class: "editor" });
      const after = () => show();

      // ---- types
      function typeForm(existing) {
        const f = {
          name: field({ name: "name", label: "Name", value: existing?.name ?? "" }),
          period: field({ name: "period", label: "Period", type: "number", min: 1, max: 10, value: existing ? String(existing.period) : "" }),
          hourly_late_fee: field({ name: "hourly_late_fee", label: "Hourly late fee", inputmode: "decimal", value: existing?.hourly_late_fee ?? "" }),
          requires_training: field({
            name: "requires_training",
            label: "Requires training",
            options: YES_NO,
            value: existing ? String(existing.requires_training) : "false",
          }),
          max_open_per_member: field({
            name: "max_open_per_member",
            label: "Max open per member",
            type: "number",
            min: 1,
            max: 3,
            value: existing ? String(existing.max_open_per_member) : "",
          }),
        };
        if (existing) return { fields: [f.name, f.period, f.hourly_late_fee, f.requires_training, f.max_open_per_member] };
        const code = field({ name: "code", label: "Code", hint: "2–20 characters: A–Z, 0–9, _." });
        const unit = field({ name: "period_unit", label: "Period unit", options: choices(["hours", "working_days"]) });
        return { fields: [code, f.name, unit, f.period, f.hourly_late_fee, f.requires_training, f.max_open_per_member] };
      }

      function openTypeEdit(type) {
        const { fields } = typeForm(type);
        const node = form({
          fields,
          submit: "Save",
          label: "Edit type",
          extra: button("Close", () => replace(editor)),
          async onSubmit(v) {
            node.fieldErrors({});
            const body = omitNull({
              name: v.name.trim() !== type.name ? v.name.trim() : null,
              period: Number(v.period) !== type.period ? Number(v.period) : null,
              hourly_late_fee: v.hourly_late_fee.trim() !== type.hourly_late_fee ? v.hourly_late_fee.trim() : null,
              requires_training: (v.requires_training === "true") !== type.requires_training ? v.requires_training === "true" : null,
              max_open_per_member:
                Number(v.max_open_per_member) !== type.max_open_per_member ? Number(v.max_open_per_member) : null,
            });
            await ctx.act(
              () => patch(`/equipment-types/${type.id}`, body),
              "Type saved.",
              after,
              (error) => node.fieldErrors(fieldProblems(error)),
            );
          },
        });
        replace(editor, section(`Edit type ${type.code}`, node));
      }

      const typeList = pagedTable({
        onError: (e) => ctx.fail(e),
        columns: [
          { label: "Code", value: (t) => t.code },
          { label: "Name", value: (t) => t.name },
          { label: "Loan period", value: periodText },
          { label: "Hourly late fee", value: (t) => fmtAmount(t.hourly_late_fee) },
          { label: "Training required", value: (t) => fmtBool(t.requires_training) },
          { label: "Max open per member", value: (t) => String(t.max_open_per_member) },
          { label: "Active", value: (t) => fmtBool(t.is_active) },
          { label: "Items total", value: (t) => String(t.items_total) },
          { label: "Items available", value: (t) => String(t.items_available) },
          ...(ctx.isAdmin
            ? [
                {
                  label: "Actions",
                  value: (t) =>
                    h(
                      "span",
                      { class: "row-actions" },
                      button("Edit", () => openTypeEdit(t)),
                      t.is_active
                        ? button("Deactivate", () =>
                            ctx.ask({
                              text: `Deactivate type ${t.code}? All booked reservations of this type will be cancelled. Open loans are not affected.`,
                              onConfirm: () => ctx.act(() => patch(`/equipment-types/${t.id}`, { is_active: false }), "Type deactivated.", after),
                            }),
                          )
                        : button("Activate", () => ctx.act(() => patch(`/equipment-types/${t.id}`, { is_active: true }), "Type activated.", after)),
                    ),
                },
              ]
            : []),
        ],
        load: (page) => get("/equipment-types", { page, page_size: 20 }),
      });

      let newType = null;
      if (ctx.isAdmin) {
        const { fields } = typeForm(null);
        newType = form({
          fields,
          submit: "Create",
          label: "New type",
          async onSubmit(v) {
            newType.fieldErrors({});
            await ctx.act(
              () =>
                post("/equipment-types", {
                  code: v.code.trim(),
                  name: v.name.trim(),
                  period_unit: v.period_unit,
                  period: v.period.trim() === "" ? null : Number(v.period),
                  hourly_late_fee: v.hourly_late_fee.trim(),
                  requires_training: v.requires_training === "true",
                  max_open_per_member: v.max_open_per_member.trim() === "" ? null : Number(v.max_open_per_member),
                }),
              (t) => `Type ${t.code} created.`,
              after,
              (error) => newType.fieldErrors(fieldProblems(error)),
            );
          },
        });
      }

      // ---- items
      const fType = field({ name: "type_id", label: "Type", options: typeOptions(types, { any: "Any" }) });
      const fBranch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
      const fStatus = field({ name: "status", label: "Status", options: choices(ITEM_STATUSES, { any: "Any" }) });
      const fQ = field({ name: "q", label: "Search", hint: "Asset tag or serial number." });

      function openItemEdit(item) {
        const serial = field({ name: "serial_no", label: "Serial number", value: item.serial_no });
        const value = field({ name: "value", label: "Value", inputmode: "decimal", value: item.value });
        const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches), value: item.branch_id });
        const node = form({
          fields: [serial, value, branch],
          submit: "Save",
          label: "Edit item",
          extra: button("Close", () => replace(editor)),
          async onSubmit(v) {
            node.fieldErrors({});
            const body = omitNull({
              serial_no: v.serial_no.trim() !== item.serial_no ? v.serial_no.trim() : null,
              value: v.value.trim() !== item.value ? v.value.trim() : null,
              branch_id: Number(v.branch_id) !== item.branch_id ? Number(v.branch_id) : null,
            });
            await ctx.act(
              () => patch(`/equipment-items/${item.id}`, body),
              "Item saved.",
              after,
              (error) => node.fieldErrors(fieldProblems(error)),
            );
          },
        });
        replace(editor, section(`Edit item ${item.asset_tag}`, node));
      }

      const itemList = pagedTable({
        onError: (e) => ctx.fail(e),
        columns: [
          { label: "Asset tag", value: (i) => i.asset_tag },
          { label: "Type", value: (i) => typeName(typeMap, i.type_id) },
          { label: "Serial number", value: (i) => i.serial_no },
          { label: "Branch", value: (i) => branchName(map, i.branch_id) },
          { label: "Value", value: (i) => fmtAmount(i.value) },
          { label: "Status", value: (i) => words(i.status) },
          { label: "Acquired on", value: (i) => fmtDate(i.acquired_on) },
          {
            label: "Actions",
            value: (i) => {
              const actions = [];
              if (ctx.isAdmin) actions.push(button("Edit", () => openItemEdit(i)));
              if (i.status === "in_repair") {
                actions.push(button("Repaired", () => ctx.act(() => post(`/equipment-items/${i.id}/repair-done`), `${i.asset_tag} is available again.`, after)));
              }
              if (ctx.isAdmin && (i.status === "available" || i.status === "in_repair")) {
                actions.push(
                  button("Retire", () =>
                    ctx.ask({
                      text: `Retire item ${i.asset_tag}? A retired item cannot be lent again.`,
                      onConfirm: () => ctx.act(() => post(`/equipment-items/${i.id}/retire`), `${i.asset_tag} retired.`, after),
                    }),
                  ),
                );
              }
              return actions.length ? h("span", { class: "row-actions" }, actions) : "–";
            },
          },
        ],
        load: (page) =>
          get("/equipment-items", {
            page,
            page_size: 20,
            type_id: fType.input.value,
            branch_id: fBranch.input.value,
            status: fStatus.input.value,
            q: fQ.input.value.trim(),
          }),
      });
      const filters = form({
        fields: [fType, fBranch, fStatus, fQ],
        submit: "Search",
        label: "Item filters",
        cls: "filters",
        onSubmit: () => {
          ctx.clearMessages();
          return itemList.goTo(1);
        },
      });

      let newItem = null;
      if (ctx.isAdmin) {
        const nType = field({ name: "type_id", label: "Type", options: typeOptions(types.filter((t) => t.is_active)) });
        const nTag = field({ name: "asset_tag", label: "Asset tag", hint: "4–20 characters: A–Z, 0–9, -." });
        const nSerial = field({ name: "serial_no", label: "Serial number" });
        const nBranch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { activeOnly: true }) });
        const nValue = field({ name: "value", label: "Value", inputmode: "decimal", hint: "1.00–100000.00" });
        const nAcquired = field({ name: "acquired_on", label: "Acquired on", type: "date", value: ctx.today, max: ctx.today });
        newItem = form({
          fields: [nType, nTag, nSerial, nBranch, nValue, nAcquired],
          submit: "Create",
          label: "New item",
          async onSubmit(v) {
            newItem.fieldErrors({});
            await ctx.act(
              () =>
                post("/equipment-items", {
                  type_id: Number(v.type_id),
                  asset_tag: v.asset_tag.trim(),
                  serial_no: v.serial_no.trim(),
                  branch_id: Number(v.branch_id),
                  value: v.value.trim(),
                  acquired_on: v.acquired_on || null,
                }),
              (i) => `Item ${i.asset_tag} created.`,
              after,
              (error) => newItem.fieldErrors(fieldProblems(error)),
            );
          },
        });
      }

      replace(
        ctx.body,
        section("Types", typeList.el),
        newType ? section("New type", newType) : null,
        section("Items", filters, itemList.el),
        newItem ? section("New item", newItem) : null,
        editor,
      );
      await Promise.all([typeList.goTo(1), itemList.goTo(1)]);
    }
    await show();
  },
};

// ---- LIB-UI-EQ-06 (part of the member page) --------------------------------------------

const trainingsScreen = {
  id: "eq-06",
  title: "Trainings",
  module: MODULE,
  roles: ["librarian", "admin"],
  part: true,
  async render(ctx) {
    replace(ctx.body, h("p", {}, "Trainings are shown on the member page."));
  },
};

async function trainingsPart(ctx, member) {
  const typeList = await loadTypes();
  const types = typeMapOf(typeList);
  const required = typeList.filter((t) => t.requires_training);
  const list = pagedTable({
    onError: (e) => ctx.fail(e),
    columns: trainingColumns(types, ctx.today),
    load: (page) => get(`/members/${member.id}/equipment-trainings`, { page, page_size: 10 }),
  });
  let recorder = h("p", {}, "No equipment type requires training.");
  if (required.length) {
    const type = field({ name: "type_id", label: "Equipment type", options: typeOptions(required) });
    const completed = field({ name: "completed_on", label: "Completed on", type: "date", value: ctx.today, max: ctx.today });
    recorder = form({
      fields: [type, completed],
      submit: "Record training",
      label: "Record training",
      async onSubmit(v) {
        recorder.fieldErrors({});
        await ctx.act(
          () => post(`/members/${member.id}/equipment-trainings`, { type_id: Number(v.type_id), completed_on: v.completed_on }),
          (t) => `Training recorded. Valid until ${fmtDate(t.valid_until)}.`,
          () => list.reload(),
          (error) => recorder.fieldErrors(fieldProblems(error)),
        );
      },
    });
  }
  const wrapper = section("Equipment trainings", recorder, list.el);
  await list.goTo(1);
  return wrapper;
}

memberPageParts.push({ id: "eq-06", render: trainingsPart });

// ---- LIB-UI-EQ-07 ------------------------------------------------------------------

const usageReportScreen = {
  id: "eq-07",
  title: "Equipment usage report",
  module: MODULE,
  roles: ["librarian", "admin"],
  async render(ctx) {
    const branches = await ctx.branches();
    const from = field({ name: "from", label: "From", type: "date", value: addDays(ctx.today, -29) });
    const to = field({ name: "to", label: "To", type: "date", value: ctx.today });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "All branches" }) });
    let query = {};
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Type", value: (r) => r.type_code },
        { label: "Loans", value: (r) => String(r.loans) },
        { label: "Late returns", value: (r) => String(r.late_returns) },
        { label: "Late hours", value: (r) => String(r.late_hours) },
        { label: "Damaged returns", value: (r) => String(r.damaged_returns) },
        { label: "Lost", value: (r) => String(r.lost) },
        { label: "Reservations", value: (r) => String(r.reservations) },
        { label: "Expired reservations", value: (r) => String(r.expired_reservations) },
        { label: "Fees created", value: (r) => fmtAmount(r.fees_created) },
      ],
      load: (page) => get("/reports/equipment-usage", { ...query, page, page_size: 50 }),
    });
    const node = form({
      fields: [from, to, branch],
      submit: "Show",
      label: "Equipment usage",
      cls: "filters",
      onSubmit(v) {
        ctx.clearMessages();
        query = { from: v.from, to: v.to, branch_id: v.branch_id };
        return list.goTo(1);
      },
    });
    replace(ctx.body, node, list.el);
    node.requestSubmit();
  },
};

export const equipmentScreens = [
  catalogScreen,
  reserveScreen,
  myEquipmentScreen,
  deskScreen,
  typesItemsScreen,
  trainingsScreen,
  usageReportScreen,
];
