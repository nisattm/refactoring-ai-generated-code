// Module 17: digital resources (e-books and databases).

import { fetchAll, get, patch, post } from "../api.js";
import { findBook, findMember } from "../context.js";
import { bookPageParts } from "../registry.js";
import {
  BOOLEAN_FILTER,
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
import { memberLink, withMembers } from "../views.js";

const MODULE = "Digital resources";
const KINDS = ["ebook", "database"];
const KIND_LABELS = { ebook: "E-book", database: "Database" };
const LICENSE_MODELS = ["perpetual", "subscription"];
const LICENSE_STATUSES = ["pending", "active", "ended", "cancelled"];
const HOLD_STATUSES = ["waiting", "ready", "fulfilled", "cancelled", "expired"];
const ORDER_STATUSES_FOR_LICENSE = new Set(["ordered", "partially_received", "received"]);
const RENEWAL_WINDOW_HOURS = 72;

const kindLabel = (kind) => KIND_LABELS[kind] || words(kind);

// ---- shared helpers ----------------------------------------------------------------

function addDays(isoDate, days) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** "YYYY-MM-DD HH:MM" of an ISO date-time moved by some hours, in the offset of the original text. */
function shiftedDateTime(iso, hours) {
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "–";
  const zone = /([+-])(\d\d):(\d\d)$/.exec(iso);
  const offset = zone ? (zone[1] === "-" ? -1 : 1) * (Number(zone[2]) * 60 + Number(zone[3])) : 0;
  return new Date(ms + hours * 3600000 + offset * 60000).toISOString().slice(0, 16).replace("T", " ");
}

// The server clock is only known when a session was just opened (started_at); otherwise the browser
// clock is used when it agrees with the session, so that remaining minutes are never invented.
let clockOffset = null;

function learnClock(session) {
  const started = Date.parse(session.started_at);
  if (!Number.isNaN(started)) clockOffset = started - Date.now();
}

function remainingMinutes(session) {
  const expires = Date.parse(session.expires_at);
  if (Number.isNaN(expires)) return null;
  if (clockOffset !== null) return Math.max(0, Math.ceil((expires - (Date.now() + clockOffset)) / 60000));
  const left = Math.ceil((expires - Date.now()) / 60000);
  return left >= 0 && left <= 61 ? Math.min(left, 60) : null;
}

const remainingText = (session) => {
  if (!session.open) return "–";
  const minutes = remainingMinutes(session);
  return minutes === null ? "–" : `${minutes} min`;
};

function resourceCache() {
  const cache = new Map();
  return (id) => {
    if (!cache.has(id)) {
      const promise = get(`/digital-resources/${id}`);
      cache.set(id, promise);
      promise.catch(() => cache.delete(id));
    }
    return cache.get(id);
  };
}

async function withResources(resourceOf, items) {
  await Promise.all(
    items.map(async (item) => {
      item._resource = await resourceOf(item.resource_id);
    }),
  );
  return items;
}

const resourceLink = (resource) => link(resource.title, `#/dig-02/${resource.id}`);

function availabilityText(resource) {
  if (resource.kind === "database") return `${resource.available} of ${resource.capacity} seats free`;
  return `${resource.available} of ${resource.capacity} copies free`;
}

async function allResources(query = {}) {
  return fetchAll("/digital-resources", query);
}

const resourceOptions = (resources, { any } = {}) =>
  recordOptions(resources, (r) => `${r.title} (${kindLabel(r.kind)})`, { any });

// ---- LIB-UI-DIG-01 -----------------------------------------------------------------

const digitalLibraryScreen = {
  id: "dig-01",
  title: "Digital library",
  module: MODULE,
  roles: ["all"],
  async render(ctx) {
    const q = field({ name: "q", label: "Title or provider" });
    const kind = field({ name: "kind", label: "Kind", options: choices(KINDS, { any: "Any", labels: KIND_LABELS }) });
    const active = field({ name: "is_active", label: "Active", options: BOOLEAN_FILTER, value: ctx.isStaff ? "" : "true" });
    const list = pagedTable({
      onError: (error) => ctx.fail(error),
      columns: [
        { label: "Title", value: (r) => resourceLink(r) },
        { label: "Kind", value: (r) => kindLabel(r.kind) },
        { label: "Provider", value: (r) => r.provider },
        { label: "Availability", value: (r) => availabilityText(r) },
        { label: "In use", value: (r) => String(r.in_use) },
        { label: "Waiting holds", value: (r) => String(r.waiting_holds) },
        { label: "Loan days", value: (r) => fmtText(r.loan_days) },
        { label: "Active", value: (r) => fmtBool(r.is_active) },
        {
          label: "Book",
          value: (r) => (r.book_id ? link("Book page", `#/cat-02/${r.book_id}`) : "–"),
        },
        { label: "Use", value: (r) => link(r.kind === "database" ? "Open" : "Borrow or hold", `#/dig-02/${r.id}`) },
      ],
      load: (page) =>
        get("/digital-resources", {
          page,
          page_size: 20,
          q: q.input.value.trim(),
          kind: kind.input.value,
          is_active: ctx.isStaff ? active.input.value : "true",
        }),
    });
    const filters = form({
      fields: ctx.isStaff ? [q, kind, active] : [q, kind],
      submit: "Search",
      label: "Filter resources",
      cls: "filters",
      onSubmit: () => {
        ctx.clearMessages();
        return list.goTo(1);
      },
    });
    replace(ctx.body, filters, list.el);
    await list.goTo(1);
  },
};

// The e-books of a book are also shown on the book page (LIB-DIG-09).
bookPageParts.push({
  id: "dig-01-book",
  async render(ctx, book) {
    const box = h("div", { class: "digital-book-part" });
    const resources = await get(`/books/${book.id}/digital-resources`);
    if (!resources.length) return box;
    box.append(
      section(
        "Digital copies",
        table({
          columns: [
            { label: "Title", value: (r) => resourceLink(r) },
            { label: "Provider", value: (r) => r.provider },
            { label: "Availability", value: (r) => availabilityText(r) },
            { label: "Waiting holds", value: (r) => String(r.waiting_holds) },
            { label: "Loan days", value: (r) => fmtText(r.loan_days) },
            { label: "Use", value: (r) => link("Borrow or hold", `#/dig-02/${r.id}`) },
          ],
          rows: resources,
        }),
      ),
    );
    return box;
  },
});

// ---- LIB-UI-DIG-02 -----------------------------------------------------------------

function sessionRows(ctx, sessions, reload) {
  return table({
    columns: [
      { label: "Started", value: (s) => fmtDateTime(s.started_at) },
      { label: "Expires", value: (s) => fmtDateTime(s.expires_at) },
      { label: "Remaining minutes", value: (s) => remainingText(s) },
      {
        label: "Actions",
        value: (s) =>
          s.open
            ? button("Close", () => ctx.act(() => post(`/digital-sessions/${s.id}/close`), "Session closed.", reload))
            : "–",
      },
    ],
    rows: sessions,
  });
}

const borrowDeskScreen = {
  id: "dig-02",
  title: "Borrow, hold, open",
  module: MODULE,
  roles: ["all"],
  async render(ctx) {
    const id = /^\d+$/.test(ctx.param) ? Number(ctx.param) : null;
    if (id === null) {
      const resources = await allResources({ is_active: "true" });
      const pick = field({ name: "resource_id", label: "Resource", options: resourceOptions(resources) });
      replace(
        ctx.body,
        form({
          fields: [pick],
          submit: "Open",
          label: "Choose a resource",
          onSubmit: (v) => {
            if (v.resource_id) ctx.navigate(`#/dig-02/${v.resource_id}`);
          },
        }),
      );
      return;
    }

    const memberNo = ctx.isStaff
      ? field({ name: "member_no", label: "Member number", hint: "For example M000001." })
      : null;
    const info = h("div", { class: "digital-info" });
    const actions = h("div", { class: "actions digital-actions" });
    const notes = h("div", { class: "digital-notes" });
    const sessionsBox = h("div", { class: "digital-sessions" });
    const result = h("div", { class: "digital-result" });
    let resource = null;

    // The member whose ready hold or sessions are shown; staff only after a member number was entered.
    async function currentMemberId() {
      if (ctx.isMember) return ctx.user.member_id;
      if (!memberNo.input.value.trim()) return null;
      try {
        return (await findMember(memberNo.input.value)).id;
      } catch {
        return null;
      }
    }

    async function actingBody() {
      if (ctx.isMember) return { resource_id: id };
      const member = await findMember(memberNo.input.value);
      return { resource_id: id, member_id: member.id };
    }

    async function load() {
      resource = await get(`/digital-resources/${id}`);
      const memberId = await currentMemberId();
      let readyHold = null;
      let openSessions = [];
      if (memberId !== null) {
        if (resource.kind === "ebook") {
          const holds = await get(`/members/${memberId}/digital-holds`, { status: "ready", page_size: 100 });
          readyHold = holds.items.find((x) => x.resource_id === id) || null;
        } else {
          const sessions = await get(`/members/${memberId}/digital-sessions`, { open: "true", resource_id: id, page_size: 100 });
          openSessions = sessions.items;
        }
      }
      replace(
        info,
        definitionList([
          ["Title", resource.title],
          ["Kind", kindLabel(resource.kind)],
          ["Provider", resource.provider],
          ["Loan days", fmtText(resource.loan_days)],
          ["Availability", availabilityText(resource)],
          ["In use", String(resource.in_use)],
          ["Waiting holds", String(resource.waiting_holds)],
          ["Active", fmtBool(resource.is_active)],
          ["Book", resource.book_id ? link("Book page", `#/cat-02/${resource.book_id}`) : "–"],
        ]),
      );
      replace(actions);
      replace(notes);
      if (resource.kind === "database") {
        actions.append(button("Open session", openSession));
        notes.append(
          h(
            "p",
            { class: "hint" },
            `A session lasts 60 minutes. ${resource.available} of ${resource.capacity} seats are free.`,
          ),
        );
        replace(sessionsBox, openSessions.length ? section("Open sessions", sessionRows(ctx, openSessions, load)) : null);
      } else {
        replace(sessionsBox);
        if (readyHold || resource.available > 0) {
          actions.append(button("Borrow", borrow));
          if (readyHold) {
            notes.append(h("p", { class: "hint" }, `Your hold is ready until ${fmtDateTime(readyHold.ready_until)}.`));
          }
        } else {
          actions.append(button("Place hold", placeHold));
          notes.append(
            h(
              "p",
              { class: "hint" },
              `No copy is free. Queue length: ${resource.waiting_holds}. The new hold would be number ${resource.waiting_holds + 1}.`,
            ),
          );
        }
      }
    }

    async function borrow() {
      ctx.clearMessages();
      let body;
      try {
        body = await actingBody();
      } catch (error) {
        ctx.fail(error);
        return;
      }
      await ctx.act(
        () => post("/digital-loans", body),
        (loan) => `Loan ${loan.id} created. Due ${fmtDateTime(loan.due_at)}.`,
        async (loan) => {
          replace(result, definitionList([["Loan", String(loan.id)], ["Due", fmtDateTime(loan.due_at)]]));
          await load();
        },
      );
    }

    async function placeHold() {
      ctx.clearMessages();
      let body;
      try {
        body = await actingBody();
      } catch (error) {
        ctx.fail(error);
        return;
      }
      await ctx.act(
        () => post("/digital-holds", body),
        (hold) => `Hold ${hold.id} placed. Queue position: ${hold.position ?? "–"}.`,
        async (hold) => {
          replace(result, definitionList([["Hold", String(hold.id)], ["Queue position", fmtText(hold.position)]]));
          await load();
        },
      );
    }

    async function openSession() {
      ctx.clearMessages();
      let body;
      try {
        body = await actingBody();
      } catch (error) {
        ctx.fail(error);
        return;
      }
      await ctx.act(
        () => post("/digital-sessions", body),
        (session) => {
          learnClock(session);
          return `Session ${session.id} open until ${fmtTime(session.expires_at)}.`;
        },
        async (session) => {
          replace(
            result,
            definitionList([
              ["Session", String(session.id)],
              ["Started", fmtDateTime(session.started_at)],
              ["Expires", fmtDateTime(session.expires_at)],
              ["Remaining minutes", remainingText(session)],
            ]),
          );
          await load();
        },
      );
    }

    if (memberNo) memberNo.input.addEventListener("change", () => load().catch((error) => ctx.fail(error)));
    replace(
      ctx.body,
      section("Resource", info),
      section("Action", memberNo, actions, notes),
      result,
      sessionsBox,
    );
    await load();
  },
};

// ---- LIB-UI-DIG-03 -----------------------------------------------------------------

const myDigitalScreen = {
  id: "dig-03",
  title: "My digital library",
  module: MODULE,
  roles: ["member"],
  async render(ctx) {
    const memberId = ctx.user.member_id;
    const resourceOf = resourceCache();

    const loans = pagedTable({
      onError: (error) => ctx.fail(error),
      columns: [
        { label: "Title", value: (l) => resourceLink(l._resource) },
        { label: "Borrowed", value: (l) => fmtDateTime(l.borrowed_at) },
        { label: "Due", value: (l) => fmtDateTime(l.due_at) },
        { label: "Status", value: (l) => l.status },
        { label: "Renewed", value: (l) => fmtBool(l.renewed) },
        {
          label: "Renewable from",
          value: (l) => (l.status === "open" && !l.renewed ? shiftedDateTime(l.due_at, -RENEWAL_WINDOW_HOURS) : "–"),
        },
        { label: "Ended", value: (l) => fmtDateTime(l.ended_at) },
        {
          label: "Actions",
          value: (l) =>
            l.status === "open"
              ? h(
                  "span",
                  { class: "row-actions" },
                  button("Return", () => ctx.act(() => post(`/digital-loans/${l.id}/return`), "Loan returned.", reloadAll)),
                  button("Renew", () =>
                    ctx.act(
                      () => post(`/digital-loans/${l.id}/renew`),
                      (done) => `Loan renewed. New due time ${fmtDateTime(done.due_at)}.`,
                      reloadAll,
                    ),
                  ),
                )
              : "–",
        },
      ],
      load: async (page) => {
        const data = await get(`/members/${memberId}/digital-loans`, { page, page_size: 10 });
        await withResources(resourceOf, data.items);
        return data;
      },
    });

    const holds = pagedTable({
      onError: (error) => ctx.fail(error),
      columns: [
        { label: "Title", value: (x) => resourceLink(x._resource) },
        { label: "Placed", value: (x) => fmtDateTime(x.created_at) },
        { label: "Status", value: (x) => x.status },
        {
          label: "Position",
          value: (x) =>
            x.status === "ready"
              ? `Ready until ${fmtDateTime(x.ready_until)}`
              : x.position !== null
                ? String(x.position)
                : "–",
        },
        { label: "Closed", value: (x) => fmtDateTime(x.closed_at) },
        {
          label: "Actions",
          value: (x) =>
            x.status === "waiting" || x.status === "ready"
              ? h(
                  "span",
                  { class: "row-actions" },
                  x.status === "ready"
                    ? button("Borrow", () =>
                        ctx.act(
                          () => post("/digital-loans", { resource_id: x.resource_id }),
                          (loan) => `Loan ${loan.id} created. Due ${fmtDateTime(loan.due_at)}.`,
                          reloadAll,
                        ),
                      )
                    : null,
                  button("Cancel", () =>
                    ctx.ask({
                      text: `Cancel your hold on ${x._resource.title}?`,
                      onConfirm: () =>
                        ctx.act(() => post(`/digital-holds/${x.id}/cancel`), "Hold cancelled.", reloadAll),
                    }),
                  ),
                )
              : "–",
        },
      ],
      load: async (page) => {
        const data = await get(`/members/${memberId}/digital-holds`, { page, page_size: 10 });
        await withResources(resourceOf, data.items);
        return data;
      },
    });

    const sessions = pagedTable({
      onError: (error) => ctx.fail(error),
      columns: [
        { label: "Title", value: (s) => resourceLink(s._resource) },
        { label: "Started", value: (s) => fmtDateTime(s.started_at) },
        { label: "Expires", value: (s) => fmtDateTime(s.expires_at) },
        { label: "Open", value: (s) => fmtBool(s.open) },
        { label: "Remaining minutes", value: (s) => remainingText(s) },
        { label: "Closed", value: (s) => fmtDateTime(s.closed_at) },
        {
          label: "Actions",
          value: (s) =>
            s.open
              ? button("Close", () => ctx.act(() => post(`/digital-sessions/${s.id}/close`), "Session closed.", reloadAll))
              : "–",
        },
      ],
      load: async (page) => {
        const data = await get(`/members/${memberId}/digital-sessions`, { page, page_size: 10 });
        await withResources(resourceOf, data.items);
        return data;
      },
    });

    const reloadAll = () => Promise.all([loans.reload(), holds.reload(), sessions.reload()]);
    replace(ctx.body, section("Loans", loans.el), section("Holds", holds.el), section("Sessions", sessions.el));
    await Promise.all([loans.goTo(1), holds.goTo(1), sessions.goTo(1)]);
  },
};

// ---- LIB-UI-DIG-04 -----------------------------------------------------------------

async function purchaseOrderOptions() {
  try {
    const orders = await fetchAll("/purchase-orders");
    const usable = orders.filter((o) => ORDER_STATUSES_FOR_LICENSE.has(o.status));
    return [{ value: "", label: "No purchase order" }, ...usable.map((o) => ({ value: o.id, label: `Order ${o.id} (${words(o.status)})` }))];
  } catch {
    return [{ value: "", label: "No purchase order" }];
  }
}

const licensesScreen = {
  id: "dig-04",
  title: "Licenses",
  module: MODULE,
  roles: ["librarian", "admin"],
  async render(ctx) {
    const resources = await allResources();
    const orderChoices = ctx.isAdmin ? await purchaseOrderOptions() : [];
    const id = /^\d+$/.test(ctx.param) ? Number(ctx.param) : null;

    const pick = field({ name: "resource_id", label: "Resource", options: resourceOptions(resources), value: id ?? undefined });
    const chooser = form({
      fields: [pick],
      submit: "Show",
      label: "Choose a resource",
      cls: "filters",
      onSubmit: (v) => {
        if (v.resource_id) ctx.navigate(`#/dig-04/${v.resource_id}`);
      },
    });

    const panel = h("div", { class: "license-panel" });
    const mainBox = h("div", { class: "license-main" });
    const expiringBox = h("div", { class: "license-expiring" });

    let licenseList = null;
    let expiringList = null;
    const reloadLicenses = async () => {
      await Promise.all([licenseList?.reload(), expiringList?.reload()]);
    };
    const afterChange = async () => {
      replace(panel);
      await reloadLicenses();
    };

    function renewPanel(lic) {
      const endsOn = field({ name: "ends_on", label: "New end date", type: "date" });
      const cost = field({ name: "cost", label: "Cost", inputmode: "decimal" });
      const order = field({ name: "order_id", label: "Purchase order", options: orderChoices });
      const node = form({
        fields: [endsOn, cost, order],
        submit: "Renew subscription",
        label: "Renew license",
        extra: button("Back", () => replace(panel)),
        async onSubmit(v) {
          node.fieldErrors({});
          await ctx.act(
            () => post(`/digital-licenses/${lic.id}/renew`, omitNull({ ends_on: text(v.ends_on), cost: text(v.cost), order_id: int(v.order_id) })),
            (created) => `License ${created.id} created from ${fmtDate(created.starts_on)} to ${fmtDate(created.ends_on)}.`,
            afterChange,
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      replace(panel, section(`Renew license ${lic.id}`, node));
    }

    function changePanel(lic) {
      const copies = field({ name: "copies", label: "Copies", type: "number", min: 1, value: lic.copies });
      const cost = field({ name: "cost", label: "Cost", inputmode: "decimal", value: lic.cost });
      const endsOn = field({ name: "ends_on", label: "End date", type: "date", value: lic.ends_on || "" });
      const fields = lic.model === "subscription" ? [copies, cost, endsOn] : [copies, cost];
      const node = form({
        fields,
        submit: "Save",
        label: "Change license",
        extra: button("Back", () => replace(panel)),
        async onSubmit(v) {
          node.fieldErrors({});
          const body = omitNull({
            copies: Number(v.copies) !== lic.copies ? int(v.copies) : null,
            cost: text(v.cost) !== lic.cost ? text(v.cost) : null,
            ends_on: v.ends_on !== undefined && text(v.ends_on) !== lic.ends_on ? text(v.ends_on) : null,
          });
          await ctx.act(
            () => patch(`/digital-licenses/${lic.id}`, body),
            "License saved.",
            afterChange,
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      replace(panel, section(`Change license ${lic.id}`, node));
    }

    const cancelLicense = (lic) =>
      ctx.ask({
        text: `Cancel license ${lic.id}? It stops counting today; open loans and sessions are not ended.`,
        onConfirm: () => ctx.act(() => post(`/digital-licenses/${lic.id}/cancel`), `License ${lic.id} cancelled.`, afterChange),
      });

    const licenseActions = (lic) => {
      if (!ctx.isAdmin) return "–";
      const buttons = [];
      if (lic.status === "pending" || lic.status === "active") buttons.push(button("Change", () => changePanel(lic)));
      if (lic.model === "subscription" && (lic.status === "active" || lic.status === "ended")) {
        buttons.push(button("Renew", () => renewPanel(lic)));
      }
      if (lic.status === "pending" || lic.status === "active") buttons.push(button("Cancel", () => cancelLicense(lic)));
      return buttons.length ? h("span", { class: "row-actions" }, buttons) : "–";
    };

    const licenseColumns = [
      { label: "ID", value: (l) => String(l.id) },
      { label: "Model", value: (l) => l.model },
      { label: "Copies", value: (l) => String(l.copies) },
      { label: "Starts on", value: (l) => fmtDate(l.starts_on) },
      { label: "Ends on", value: (l) => fmtDate(l.ends_on) },
      { label: "Cost", value: (l) => fmtAmount(l.cost) },
      { label: "Purchase order", value: (l) => fmtText(l.order_id) },
      { label: "Cancelled on", value: (l) => fmtDate(l.cancelled_on) },
      { label: "Status", value: (l) => l.status },
      { label: "Actions", value: (l) => licenseActions(l) },
    ];

    if (id !== null) {
      const resource = await get(`/digital-resources/${id}`);
      const status = field({ name: "status", label: "Status", options: choices(LICENSE_STATUSES, { any: "Any" }) });
      licenseList = pagedTable({
        onError: (error) => ctx.fail(error),
        columns: licenseColumns,
        load: (page) => get(`/digital-resources/${id}/licenses`, { page, page_size: 10, status: status.input.value }),
      });
      const statusForm = form({
        fields: [status],
        submit: "Filter",
        label: "Filter licenses",
        cls: "filters",
        onSubmit: () => licenseList.goTo(1),
      });

      const parts = [
        section(
          `Licenses of ${resource.title}`,
          definitionList([
            ["Kind", kindLabel(resource.kind)],
            ["Capacity now", String(resource.capacity)],
            ["Active", fmtBool(resource.is_active)],
          ]),
          statusForm,
          licenseList.el,
        ),
      ];

      if (ctx.isAdmin) {
        const model = field({ name: "model", label: "Model", options: choices(LICENSE_MODELS, {}) });
        const copies = field({
          name: "copies",
          label: resource.kind === "database" ? "Concurrent seats" : "Copies",
          type: "number",
          min: 1,
          value: "1",
        });
        const startsOn = field({ name: "starts_on", label: "Starts on", type: "date", value: ctx.today });
        const endsOn = field({ name: "ends_on", label: "Ends on", type: "date", hint: "Subscriptions only." });
        const cost = field({ name: "cost", label: "Cost", inputmode: "decimal", value: "0.00" });
        const order = field({ name: "order_id", label: "Purchase order", options: orderChoices });
        const addForm = form({
          fields: [model, copies, startsOn, endsOn, cost, order],
          submit: "Add license",
          label: "Add license",
          async onSubmit(v) {
            addForm.fieldErrors({});
            await ctx.act(
              () =>
                post(
                  `/digital-resources/${id}/licenses`,
                  omitNull({
                    model: v.model,
                    copies: int(v.copies),
                    starts_on: text(v.starts_on),
                    ends_on: v.model === "subscription" ? text(v.ends_on) : null,
                    cost: text(v.cost),
                    order_id: int(v.order_id),
                  }),
                ),
              (lic) => `License ${lic.id} added (${lic.status}).`,
              reloadLicenses,
              (error) => addForm.fieldErrors(fieldProblems(error)),
            );
          },
        });
        parts.push(section("Add license", addForm));
      }
      replace(mainBox, ...parts);
    }

    const within = field({ name: "ending_within_days", label: "Ending within days", type: "number", min: 1, max: 365, value: "30" });
    expiringList = pagedTable({
      onError: (error) => ctx.fail(error),
      columns: [
        { label: "Resource", value: (l) => link(l.resource_title, `#/dig-04/${l.resource_id}`) },
        { label: "Copies", value: (l) => String(l.copies) },
        { label: "Ends on", value: (l) => fmtDate(l.ends_on) },
        { label: "Cost", value: (l) => fmtAmount(l.cost) },
        { label: "Actions", value: (l) => (ctx.isAdmin ? button("Renew", () => renewPanel(l)) : "–") },
      ],
      load: (page) => get("/digital-licenses", { page, page_size: 10, ending_within_days: within.input.value.trim() }),
    });
    const withinForm = form({
      fields: [within],
      submit: "Show",
      label: "Expiring subscriptions",
      cls: "filters",
      onSubmit: () => {
        ctx.clearMessages();
        return expiringList.goTo(1);
      },
    });
    replace(expiringBox, section("Subscriptions ending soon", withinForm, expiringList.el));

    replace(ctx.body, chooser, mainBox, panel, expiringBox);
    await Promise.all([licenseList?.goTo(1), expiringList.goTo(1)]);
  },
};

// ---- LIB-UI-DIG-05 -----------------------------------------------------------------

const resourcesScreen = {
  id: "dig-05",
  title: "Resources",
  module: MODULE,
  roles: ["librarian", "admin"],
  async render(ctx) {
    const panel = h("div", { class: "resource-panel" });
    const problemsOf = (error) => {
      const problems = fieldProblems(error);
      if (problems.book_id) problems.isbn = problems.book_id;
      return problems;
    };
    async function bookIdOf(isbn) {
      const wanted = text(isbn);
      return wanted === null ? null : (await findBook(wanted)).id;
    }

    const q = field({ name: "q", label: "Title or provider" });
    const kind = field({ name: "kind", label: "Kind", options: choices(KINDS, { any: "Any", labels: KIND_LABELS }) });
    const active = field({ name: "is_active", label: "Active", options: BOOLEAN_FILTER });
    const list = pagedTable({
      onError: (error) => ctx.fail(error),
      columns: [
        { label: "ID", value: (r) => String(r.id) },
        { label: "Title", value: (r) => r.title },
        { label: "Kind", value: (r) => kindLabel(r.kind) },
        { label: "Provider", value: (r) => r.provider },
        { label: "Book", value: (r) => (r.book_id ? link("Book page", `#/cat-02/${r.book_id}`) : "–") },
        { label: "Loan days", value: (r) => fmtText(r.loan_days) },
        { label: "Capacity", value: (r) => String(r.capacity) },
        { label: "Active", value: (r) => fmtBool(r.is_active) },
        {
          label: "Actions",
          value: (r) =>
            h(
              "span",
              { class: "row-actions" },
              button("Edit", () => openEdit(r)),
              r.is_active
                ? button("Deactivate", () =>
                    ctx.ask({
                      text: `Deactivate ${r.title}? Its waiting and ready holds will be cancelled and its open sessions closed; open loans run until they are due.`,
                      onConfirm: () =>
                        ctx.act(() => patch(`/digital-resources/${r.id}`, { is_active: false }), "Resource deactivated.", afterChange),
                    }),
                  )
                : button("Activate", () =>
                    ctx.act(() => patch(`/digital-resources/${r.id}`, { is_active: true }), "Resource activated.", afterChange),
                  ),
            ),
        },
      ],
      load: (page) =>
        get("/digital-resources", {
          page,
          page_size: 20,
          q: q.input.value.trim(),
          kind: kind.input.value,
          is_active: active.input.value,
        }),
    });
    const afterChange = async () => {
      replace(panel);
      await list.reload();
    };
    const filters = form({
      fields: [q, kind, active],
      submit: "Search",
      label: "Filter resources",
      cls: "filters",
      onSubmit: () => {
        ctx.clearMessages();
        return list.goTo(1);
      },
    });

    async function openEdit(resource) {
      let currentIsbn = "";
      if (resource.book_id) currentIsbn = (await ctx.book(resource.book_id)).isbn;
      const title = field({ name: "title", label: "Title", value: resource.title });
      const provider = field({ name: "provider", label: "Provider", value: resource.provider });
      const isbn = field({ name: "isbn", label: "Book (ISBN)", value: currentIsbn, hint: "E-books only; leave empty for none." });
      const loanDays = field({ name: "loan_days", label: "Loan days", type: "number", min: 1, max: 21, value: resource.loan_days ?? "" });
      const fields = resource.kind === "ebook" ? [title, provider, isbn, loanDays] : [title, provider];
      const node = form({
        fields,
        submit: "Save",
        label: "Edit resource",
        extra: button("Close", () => replace(panel)),
        async onSubmit(v) {
          node.fieldErrors({});
          const body = {};
          if (v.title.trim() !== resource.title) body.title = v.title.trim();
          if (v.provider.trim() !== resource.provider) body.provider = v.provider.trim();
          try {
            if (resource.kind === "ebook") {
              if ((text(v.isbn) ?? "") !== currentIsbn) body.book_id = await bookIdOf(v.isbn);
              const days = int(v.loan_days);
              if (days !== null && days !== resource.loan_days) body.loan_days = days;
            }
          } catch (error) {
            ctx.fail(error);
            return;
          }
          await ctx.act(
            () => patch(`/digital-resources/${resource.id}`, body),
            "Resource saved.",
            afterChange,
            (error) => node.fieldErrors(problemsOf(error)),
          );
        },
      });
      replace(panel, section(`Edit ${resource.title}`, node));
    }

    const kindField = field({ name: "kind", label: "Kind", options: choices(KINDS, { labels: KIND_LABELS }) });
    const title = field({ name: "title", label: "Title" });
    const provider = field({ name: "provider", label: "Provider" });
    const isbn = field({ name: "isbn", label: "Book (ISBN)", hint: "E-books only; optional." });
    const loanDays = field({ name: "loan_days", label: "Loan days", type: "number", min: 1, max: 21, hint: "E-books: 1–21, default 14. Not for databases." });
    const createForm = form({
      fields: [kindField, title, provider, isbn, loanDays],
      submit: "Create",
      label: "Create resource",
      async onSubmit(v) {
        createForm.fieldErrors({});
        let bookId = null;
        try {
          bookId = await bookIdOf(v.isbn);
        } catch (error) {
          ctx.fail(error);
          createForm.fieldErrors({ isbn: error.message });
          return;
        }
        const created = await ctx.act(
          () =>
            post(
              "/digital-resources",
              omitNull({ kind: v.kind, title: v.title.trim(), provider: v.provider.trim(), book_id: bookId, loan_days: int(v.loan_days) }),
            ),
          (r) => `Resource ${r.id} created.`,
          list.reload,
          (error) => createForm.fieldErrors(problemsOf(error)),
        );
        if (created) {
          title.input.value = "";
          provider.input.value = "";
          isbn.input.value = "";
          loanDays.input.value = "";
        }
      },
    });

    replace(ctx.body, section("New resource", createForm), panel, filters, list.el);
    await list.goTo(1);
  },
};

// ---- LIB-UI-DIG-06 -----------------------------------------------------------------

const digitalDeskScreen = {
  id: "dig-06",
  title: "Digital desk",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const id = /^\d+$/.test(ctx.param) ? Number(ctx.param) : null;
    const resources = await allResources({ kind: "ebook" });

    const processBox = h("div", { class: "digital-process" });
    const processButton = button("Process", () =>
      ctx.act(
        () => post("/digital/process"),
        (r) =>
          `Processed: ${r.expired_loans} loans expired, ${r.expired_holds} holds expired, ${r.holds_ready} holds ready, ${r.due_soon_notices} due-soon notices.`,
        async (r) => {
          replace(
            processBox,
            definitionList([
              ["Expired loans", String(r.expired_loans)],
              ["Expired holds", String(r.expired_holds)],
              ["Holds ready", String(r.holds_ready)],
              ["Due-soon notices", String(r.due_soon_notices)],
            ]),
          );
          await queue?.reload();
        },
      ),
    );

    const pick = field({ name: "resource_id", label: "Resource", options: resourceOptions(resources), value: id ?? undefined });
    const status = field({ name: "status", label: "Status", options: choices(HOLD_STATUSES), value: "waiting" });
    let queue = null;
    const queueBox = h("div", { class: "digital-queue" });

    if (id !== null) {
      queue = pagedTable({
        onError: (error) => ctx.fail(error),
        columns: [
          { label: "Position", value: (x) => fmtText(x.position) },
          { label: "Member", value: (x) => (x._member ? memberLink(x._member) : `#${x.member_id}`) },
          { label: "Placed", value: (x) => fmtDateTime(x.created_at) },
          { label: "Status", value: (x) => x.status },
          { label: "Ready until", value: (x) => fmtDateTime(x.ready_until) },
          {
            label: "Actions",
            value: (x) =>
              x.status === "waiting" || x.status === "ready"
                ? button("Cancel", () =>
                    ctx.ask({
                      text: `Cancel hold ${x.id}?`,
                      onConfirm: () => ctx.act(() => post(`/digital-holds/${x.id}/cancel`), "Hold cancelled.", () => queue.reload()),
                    }),
                  )
                : "–",
          },
        ],
        load: async (page) => {
          const data = await get(`/digital-resources/${id}/holds`, { page, page_size: 20, status: status.input.value });
          await withMembers(ctx, data.items);
          return data;
        },
      });
      replace(queueBox, queue.el);
    }

    const chooser = form({
      fields: [pick, status],
      submit: "Show",
      label: "Hold queue",
      cls: "filters",
      onSubmit: (v) => {
        ctx.clearMessages();
        if (!v.resource_id) return undefined;
        if (Number(v.resource_id) === id && queue) return queue.goTo(1);
        return ctx.navigate(`#/dig-06/${v.resource_id}`);
      },
    });

    replace(
      ctx.body,
      section("Processing", h("div", { class: "actions" }, processButton), processBox),
      section("Hold queue", chooser, queueBox),
    );
    await queue?.goTo(1);
  },
};

// ---- LIB-UI-DIG-07 -----------------------------------------------------------------

const usageReportScreen = {
  id: "dig-07",
  title: "Digital usage report",
  module: MODULE,
  roles: ["librarian", "admin"],
  async render(ctx) {
    const from = field({ name: "from", label: "From", type: "date", value: addDays(ctx.today, -29) });
    const to = field({ name: "to", label: "To", type: "date", value: ctx.today });
    const kind = field({ name: "kind", label: "Kind", options: choices(KINDS, { any: "Any", labels: KIND_LABELS }) });
    const list = pagedTable({
      onError: (error) => ctx.fail(error),
      columns: [
        { label: "Title", value: (r) => link(r.title, `#/dig-02/${r.resource_id}`) },
        { label: "Kind", value: (r) => kindLabel(r.kind) },
        { label: "Loans", value: (r) => String(r.loans) },
        { label: "Renewals", value: (r) => String(r.renewals) },
        { label: "Holds placed", value: (r) => String(r.holds_placed) },
        { label: "Holds expired", value: (r) => String(r.holds_expired) },
        { label: "Sessions", value: (r) => String(r.sessions) },
        { label: "License cost", value: (r) => fmtAmount(r.license_cost) },
      ],
      load: (page) =>
        get("/reports/digital-usage", { page, page_size: 20, from: from.input.value, to: to.input.value, kind: kind.input.value }),
    });
    const node = form({
      fields: [from, to, kind],
      submit: "Show",
      label: "Digital usage",
      cls: "filters",
      onSubmit: () => {
        ctx.clearMessages();
        return list.goTo(1);
      },
    });
    replace(ctx.body, node, list.el);
    await list.goTo(1);
  },
};

export const digitalScreens = [
  digitalLibraryScreen,
  borrowDeskScreen,
  myDigitalScreen,
  licensesScreen,
  resourcesScreen,
  digitalDeskScreen,
  usageReportScreen,
];
