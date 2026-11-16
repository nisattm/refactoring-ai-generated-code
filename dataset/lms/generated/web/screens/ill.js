// Module 18: interlibrary loans (WEB_INTERFACE.md, section 3.4).

import { fetchAll, get, patch, post } from "../api.js";
import { findBook, findMember } from "../context.js";
import {
  BOOLEAN_FILTER,
  branchOptions,
  button,
  choices,
  definitionList,
  field,
  fieldProblems,
  fmtAmount,
  fmtBool,
  fmtDate,
  fmtText,
  form,
  h,
  link,
  omitNull,
  pagedTable,
  recordOptions,
  replace,
  section,
  text,
  words,
} from "../ui.js";
import { branchMap, branchName, memberLink, withMembers } from "../views.js";

const MODULE = "Interlibrary loans";

const REQUEST_STATUSES = ["requested", "sent", "rejected", "received", "on_loan", "returned", "uncollected", "closed", "cancelled", "lost"];
const OUTGOING_STATUSES = ["requested", "shipped", "declined", "returned", "lost"];
const CANCELLABLE = ["requested", "sent", "rejected"];

const ACTIVE_OPTIONS = [
  { value: "true", label: "Yes" },
  { value: "false", label: "No" },
];

// ---- helpers ---------------------------------------------------------------------

function addDays(isoDate, days) {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

const isDate = (value) => /^\d{4}-\d{2}-\d{2}$/.test(value);

/** LIB-ILL-12: the 3rd working day before `partnerDue`, counting back from the day before it. */
async function memberDueOn(partnerDue) {
  let day = partnerDue;
  let counted = 0;
  for (let i = 0; i < 60 && counted < 3; i += 1) {
    day = addDays(day, -1);
    const info = await get(`/calendar/days/${day}`);
    if (info.working_day) counted += 1;
  }
  return day;
}

/** A line under a `partner_due_on` field that shows the member due date before saving. */
function duePreview(ctx, dateField, { minDate } = {}) {
  const el = h("p", { class: "due-preview", "aria-live": "polite" });
  let ticket = 0;
  async function update() {
    const mine = (ticket += 1);
    const value = dateField.input.value;
    if (!isDate(value)) {
      replace(el);
      return;
    }
    try {
      const due = await memberDueOn(value);
      if (mine !== ticket) return;
      const short = minDate && due < minDate ? " This is earlier than 7 days from today; the server will refuse it." : "";
      replace(el, "Member due date: ", h("strong", {}, fmtDate(due)), short);
    } catch (error) {
      if (mine === ticket) ctx.fail(error);
    }
  }
  dateField.input.addEventListener("input", update);
  dateField.input.addEventListener("change", update);
  return { el, update };
}

function insertBeforeActions(node, element) {
  node.insertBefore(element, node.querySelector(".actions"));
}

async function partnerList(ctx) {
  const partners = await fetchAll("/ill-partners");
  const map = new Map(partners.map((p) => [p.id, p]));
  return { partners, map };
}

const partnerLabel = (p) => `${p.code} – ${p.name}`;
const partnerName = (map, id) => (id === null || id === undefined ? "–" : map.get(id)?.code || `#${id}`);

function requestDetails(r) {
  const parts = [];
  if (r.reject_reason) parts.push(`Rejected: ${r.reject_reason}`);
  if (r.cancel_reason) parts.push(`Cancelled: ${words(r.cancel_reason)}`);
  if (r.renewal !== "none") parts.push(`Renewal ${r.renewal}`);
  return parts.length ? parts.join("; ") : "–";
}

function requestColumns({ branchMapById, partnerMapById, withMember, actions }) {
  const columns = [{ label: "ID", value: (r) => String(r.id) }];
  if (withMember) columns.push({ label: "Member", value: (r) => (r._member ? memberLink(r._member) : `#${r.member_id}`) });
  columns.push(
    { label: "Title", value: (r) => r.title },
    { label: "Author", value: (r) => r.author },
    { label: "ISBN", value: (r) => fmtText(r.isbn) },
    { label: "Status", value: (r) => r.status },
  );
  if (partnerMapById) {
    columns.push(
      { label: "Partner", value: (r) => partnerName(partnerMapById, r.partner_id) },
      { label: "Tried", value: (r) => (r.tried_partner_ids.length ? r.tried_partner_ids.map((id) => partnerName(partnerMapById, id)).join(", ") : "–") },
    );
  }
  columns.push(
    { label: "Pickup branch", value: (r) => branchName(branchMapById, r.pickup_branch_id) },
    { label: "Collect until", value: (r) => fmtDate(r.collect_until) },
  );
  if (withMember) columns.push({ label: "Partner due date", value: (r) => fmtDate(r.partner_due_on) });
  columns.push(
    { label: "Due date", value: (r) => fmtDate(r.due_on) },
    { label: "Overdue", value: (r) => fmtBool(r.overdue) },
    { label: "Late fee", value: (r) => fmtAmount(r.accrued_late_fee) },
    { label: "Notes", value: requestDetails },
  );
  if (actions) columns.push({ label: "Actions", value: (r) => actions(r) });
  return columns;
}

// ---- LIB-UI-ILL-01 ---------------------------------------------------------------

const requestScreen = {
  id: "ill-01",
  title: "Request a book from another library",
  module: MODULE,
  roles: ["member", "librarian", "admin"],
  async render(ctx) {
    const memberNo = ctx.isStaff ? field({ name: "member_no", label: "Member number", hint: "For example M000001." }) : null;
    const title = field({ name: "title", label: "Title" });
    const author = field({ name: "author", label: "Author" });
    const isbn = field({ name: "isbn", label: "ISBN", hint: "Optional." });
    const result = h("div", { class: "ill-result" });

    const node = form({
      fields: [memberNo, title, author, isbn].filter(Boolean),
      submit: "Request",
      label: "Request a book",
      async onSubmit(v) {
        node.fieldErrors({});
        ctx.clearMessages();
        let body;
        try {
          body = { title: v.title.trim(), author: v.author.trim(), isbn: text(v.isbn) };
          if (ctx.isStaff) body.member_id = (await findMember(v.member_no)).id;
        } catch (error) {
          ctx.fail(error);
          return;
        }
        const created = await ctx.act(
          () => post("/ill-requests", omitNull(body)),
          (r) => `Request ${r.id} created with status ${r.status}.`,
          undefined,
          (error) => {
            const problems = fieldProblems(error);
            if (problems.member_id) problems.member_no = problems.member_id;
            node.fieldErrors(problems);
            replace(result);
            if (error.code === "AVAILABLE_LOCALLY" && error.details?.book_id) {
              ctx.messages.firstElementChild?.append(
                h("p", {}, "This book is available in the library: ", link("Open the book page", `#/cat-02/${error.details.book_id}`)),
              );
            }
          },
        );
        if (created) {
          title.input.value = "";
          author.input.value = "";
          isbn.input.value = "";
          replace(
            result,
            section(
              "New request",
              definitionList([
                ["Request", String(created.id)],
                ["Title", created.title],
                ["Author", created.author],
                ["ISBN", fmtText(created.isbn)],
                ["Status", created.status],
              ]),
              ctx.isMember ? link("My interlibrary requests", "#/ill-02") : null,
            ),
          );
        }
      },
    });
    replace(ctx.body, node, result);
  },
};

// ---- LIB-UI-ILL-02 ---------------------------------------------------------------

const myRequestsScreen = {
  id: "ill-02",
  title: "My interlibrary requests",
  module: MODULE,
  roles: ["member"],
  async render(ctx) {
    const map = await branchMap(ctx);
    const me = await get("/members/me");
    const status = field({ name: "status", label: "Status", options: choices(REQUEST_STATUSES, { any: "Any" }) });
    const reload = () => list.reload();

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      rowClass: (r) => (r.overdue ? "overdue" : undefined),
      columns: requestColumns({
        branchMapById: map,
        actions: (r) => {
          const buttons = [];
          if (CANCELLABLE.includes(r.status)) {
            buttons.push(
              button("Cancel", () =>
                ctx.ask({
                  text: `Cancel the request for "${r.title}"?`,
                  onConfirm: () => ctx.act(() => post(`/ill-requests/${r.id}/cancel`), "Request cancelled.", reload),
                }),
              ),
            );
          }
          if (r.status === "on_loan" && !r.overdue && r.renewal === "none") {
            buttons.push(button("Ask for more time", () => ctx.act(() => post(`/ill-requests/${r.id}/renewal-request`), "Your request for more time was sent.", reload)));
          }
          return buttons.length ? h("span", { class: "row-actions" }, buttons) : "–";
        },
      }),
      load: (page) => get(`/members/${me.id}/ill-requests`, { page, page_size: 20, status: status.input.value }),
    });
    const filters = form({
      fields: [status],
      submit: "Filter",
      label: "Request filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    replace(ctx.body, filters, list.el);
    await list.goTo(1);
  },
};

// ---- LIB-UI-ILL-03 ---------------------------------------------------------------

const incomingDeskScreen = {
  id: "ill-03",
  title: "Interlibrary desk (incoming)",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const branchMapById = await branchMap(ctx);
    const { partners, map: partnerMapById } = await partnerList(ctx);
    const panel = h("div", { class: "ill-panel" });
    let panelOpen = false;

    const status = field({ name: "status", label: "Status", options: choices(REQUEST_STATUSES, { any: "Any" }) });
    const partner = field({ name: "partner_id", label: "Partner", options: recordOptions(partners, partnerLabel, { any: "Any" }) });
    const overdue = field({ name: "overdue", label: "Overdue", options: BOOLEAN_FILTER });
    const memberNo = field({ name: "member_no", label: "Member number" });

    function closePanel() {
      panelOpen = false;
      replace(panel);
      return list.reload();
    }
    const reload = () => list.reload();
    const done = (message) => (run) => ctx.act(run, message, closePanel);

    function showPanel(title, node) {
      panelOpen = true;
      replace(panel, section(title, node));
      list.reload();
    }

    function openSend(r) {
      const options = partners.filter((p) => p.is_active && !r.tried_partner_ids.includes(p.id));
      const choice = field({ name: "partner_id", label: "Partner", options: recordOptions(options, partnerLabel) });
      const tried = r.tried_partner_ids.length
        ? h("p", {}, `Already tried: ${r.tried_partner_ids.map((id) => partnerName(partnerMapById, id)).join(", ")}.`)
        : null;
      const node = form({
        fields: [choice],
        submit: "Send",
        label: "Send to a partner",
        extra: button("Back", closePanel),
        onSubmit(v) {
          if (!v.partner_id) {
            choice.setError("Choose a partner.");
            return undefined;
          }
          return ctx.act(() => post(`/ill-requests/${r.id}/send`, { partner_id: Number(v.partner_id) }), `Request ${r.id} sent.`, closePanel);
        },
      });
      if (tried) node.insertBefore(tried, node.firstChild);
      showPanel(`Send request ${r.id}: ${r.title}`, node);
    }

    function openReject(r) {
      const reason = field({ name: "reason", label: "Reason", hint: "1–200 characters." });
      const node = form({
        fields: [reason],
        submit: "Reject",
        label: "Record a rejection",
        extra: button("Back", closePanel),
        onSubmit(v) {
          node.fieldErrors({});
          return ctx.act(
            () => post(`/ill-requests/${r.id}/reject`, { reason: v.reason.trim() }),
            `Request ${r.id} rejected.`,
            closePanel,
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      showPanel(`Reject request ${r.id}: ${r.title}`, node);
    }

    function openReceive(r) {
      const due = field({ name: "partner_due_on", label: "Partner due date", type: "date" });
      const cost = field({ name: "replacement_cost", label: "Replacement cost", inputmode: "decimal", hint: "0.01–100000.00" });
      const pickup = field({ name: "pickup_branch_id", label: "Pickup branch", options: branchOptions(branches, { activeOnly: true }) });
      const preview = duePreview(ctx, due, { minDate: addDays(ctx.today, 7) });
      const node = form({
        fields: [due, cost, pickup],
        submit: "Receive",
        label: "Receive a book",
        extra: button("Back", closePanel),
        onSubmit(v) {
          node.fieldErrors({});
          return ctx.act(
            () =>
              post(`/ill-requests/${r.id}/receive`, {
                partner_due_on: v.partner_due_on,
                replacement_cost: v.replacement_cost.trim(),
                pickup_branch_id: Number(v.pickup_branch_id),
              }),
            (x) => `Request ${x.id} received. Member due date: ${fmtDate(x.due_on)}. Collect until ${fmtDate(x.collect_until)}.`,
            closePanel,
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      insertBeforeActions(node, preview.el);
      showPanel(`Receive request ${r.id}: ${r.title}`, node);
    }

    function openReturn(r) {
      const branch = field({ name: "branch_id", label: "Return branch", options: branchOptions(branches, { activeOnly: true }) });
      const node = form({
        fields: [branch],
        submit: "Return",
        label: "Return a book",
        extra: button("Back", closePanel),
        onSubmit(v) {
          return ctx.act(
            () => post(`/ill-requests/${r.id}/return`, { branch_id: Number(v.branch_id) }),
            (x) => `Request ${x.id} returned on ${fmtDate(x.returned_on)}.`,
            closePanel,
          );
        },
      });
      showPanel(`Return request ${r.id}: ${r.title}`, node);
    }

    function openRenewal(r) {
      const approved = field({ name: "approved", label: "Approved", options: ACTIVE_OPTIONS });
      const due = field({ name: "partner_due_on", label: "New partner due date", type: "date", hint: `Now ${fmtDate(r.partner_due_on)}; needed when approved.` });
      const preview = duePreview(ctx, due);
      const node = form({
        fields: [approved, due],
        submit: "Answer",
        label: "Answer a renewal request",
        extra: button("Back", closePanel),
        onSubmit(v) {
          node.fieldErrors({});
          const body = v.approved === "true" ? { approved: true, partner_due_on: v.partner_due_on } : { approved: false };
          return ctx.act(
            () => post(`/ill-requests/${r.id}/renewal-answer`, body),
            (x) => `Renewal ${x.renewal}.${x.renewal === "approved" ? ` New due date: ${fmtDate(x.due_on)}.` : ""}`,
            closePanel,
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      insertBeforeActions(node, preview.el);
      showPanel(`Answer the renewal request ${r.id}: ${r.title}`, node);
    }

    const opener = (label, open) => (panelOpen ? null : button(label, open));

    function actions(r) {
      const buttons = [];
      if (r.status === "requested" || r.status === "rejected") buttons.push(opener("Send", () => openSend(r)));
      if (r.status === "sent") {
        buttons.push(opener("Reject", () => openReject(r)));
        buttons.push(opener("Receive", () => openReceive(r)));
      }
      if (r.status === "received") buttons.push(button("Collect", () => done(`Request ${r.id} collected.`)(() => post(`/ill-requests/${r.id}/collect`))));
      if (r.status === "on_loan") {
        buttons.push(opener("Return", () => openReturn(r)));
        if (r.renewal === "requested") buttons.push(opener("Answer renewal", () => openRenewal(r)));
        buttons.push(button("Report lost", () => done(`Request ${r.id} reported lost.`)(() => post(`/ill-requests/${r.id}/report-lost`))));
      }
      if (r.status === "returned" || r.status === "uncollected") {
        buttons.push(button("Close", () => done(`Request ${r.id} closed.`)(() => post(`/ill-requests/${r.id}/close`))));
      }
      if (CANCELLABLE.includes(r.status)) {
        buttons.push(
          button("Cancel", () =>
            ctx.ask({
              text: `Cancel request ${r.id} "${r.title}"?`,
              onConfirm: () => ctx.act(() => post(`/ill-requests/${r.id}/cancel`), `Request ${r.id} cancelled.`, reload),
            }),
          ),
        );
      }
      const shown = buttons.filter(Boolean);
      return shown.length ? h("span", { class: "row-actions" }, shown) : "–";
    }

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      rowClass: (r) => (r.overdue ? "overdue" : undefined),
      columns: requestColumns({ branchMapById, partnerMapById, withMember: true, actions }),
      load: async (page) => {
        const query = { page, page_size: 20, status: status.input.value, partner_id: partner.input.value, overdue: overdue.input.value };
        if (memberNo.input.value.trim()) query.member_id = (await findMember(memberNo.input.value)).id;
        const data = await get("/ill-requests", query);
        await withMembers(ctx, data.items);
        return data;
      },
    });

    const filters = form({
      fields: [status, partner, overdue, memberNo],
      submit: "Filter",
      label: "Request filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });

    const processBox = h(
      "div",
      { class: "actions" },
      button("Process", () =>
        ctx.act(
          () => post("/ill/process"),
          (r) => `Processed: ${r.uncollected} uncollected, ${r.overdue_outgoing} overdue outgoing.`,
          reload,
        ),
      ),
    );
    replace(ctx.body, processBox, filters, panel, list.el);
    await list.goTo(1);
  },
};

// ---- LIB-UI-ILL-04 ---------------------------------------------------------------

const outgoingDeskScreen = {
  id: "ill-04",
  title: "Interlibrary desk (outgoing)",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const branchMapById = await branchMap(ctx);
    const { partners, map: partnerMapById } = await partnerList(ctx);
    const panel = h("div", { class: "ill-panel" });
    let panelOpen = false;

    const status = field({ name: "status", label: "Status", options: choices(OUTGOING_STATUSES, { any: "Any" }) });
    const partnerFilter = field({ name: "partner_id", label: "Partner", options: recordOptions(partners, partnerLabel, { any: "Any" }) });
    const overdue = field({ name: "overdue", label: "Overdue", options: BOOLEAN_FILTER });

    function closePanel() {
      panelOpen = false;
      replace(panel);
      return list.reload();
    }
    const reload = () => list.reload();

    function showPanel(title, node) {
      panelOpen = true;
      replace(panel, section(title, node));
      list.reload();
    }
    const opener = (label, open) => (panelOpen ? null : button(label, open));

    async function openShip(o) {
      let copies;
      try {
        copies = await fetchAll(`/books/${o.book_id}/copies`, { status: "available" });
      } catch (error) {
        ctx.fail(error);
        return;
      }
      const options = copies.map((c) => ({ value: c.id, label: `${c.barcode} – ${branchName(branchMapById, c.current_branch_id)}${c.shelf_location ? ` (${c.shelf_location})` : ""}` }));
      let node;
      if (!options.length) {
        node = h("div", {}, h("p", {}, "No copy of this book is available."), button("Back", closePanel));
      } else {
        const copy = field({ name: "copy_id", label: "Copy", options });
        node = form({
          fields: [copy],
          submit: "Ship",
          label: "Ship a copy",
          extra: button("Back", closePanel),
          onSubmit(v) {
            return ctx.act(
              () => post(`/ill-outgoing/${o.id}/ship`, { copy_id: Number(v.copy_id) }),
              (x) => `Request ${x.id} shipped. Due date: ${fmtDate(x.due_on)}.`,
              closePanel,
            );
          },
        });
      }
      showPanel(`Ship request ${o.id}: ${o.book_title}`, node);
    }

    function openReturned(o) {
      const branch = field({ name: "branch_id", label: "Return branch", options: branchOptions(branches, { activeOnly: true }) });
      const node = form({
        fields: [branch],
        submit: "Returned",
        label: "Record the return",
        extra: button("Back", closePanel),
        onSubmit(v) {
          return ctx.act(() => post(`/ill-outgoing/${o.id}/returned`, { branch_id: Number(v.branch_id) }), `Request ${o.id} returned.`, closePanel);
        },
      });
      showPanel(`Returned request ${o.id}: ${o.book_title}`, node);
    }

    function actions(o) {
      const buttons = [];
      if (o.status === "requested") {
        buttons.push(opener("Ship", () => openShip(o)));
        buttons.push(button("Decline", () => ctx.act(() => post(`/ill-outgoing/${o.id}/decline`), `Request ${o.id} declined.`, closePanel)));
      }
      if (o.status === "shipped") {
        buttons.push(opener("Returned", () => openReturned(o)));
        buttons.push(button("Report lost", () => ctx.act(() => post(`/ill-outgoing/${o.id}/report-lost`), `Request ${o.id} reported lost.`, closePanel)));
      }
      const shown = buttons.filter(Boolean);
      return shown.length ? h("span", { class: "row-actions" }, shown) : "–";
    }

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      rowClass: (o) => (o.overdue ? "overdue" : undefined),
      columns: [
        { label: "ID", value: (o) => String(o.id) },
        { label: "Partner", value: (o) => partnerName(partnerMapById, o.partner_id) },
        { label: "Title", value: (o) => link(o.book_title, `#/cat-02/${o.book_id}`) },
        { label: "Barcode", value: (o) => fmtText(o.barcode) },
        { label: "Status", value: (o) => o.status },
        { label: "Shipped on", value: (o) => fmtDate(o.shipped_on) },
        { label: "Due date", value: (o) => fmtDate(o.due_on) },
        { label: "Overdue", value: (o) => (o.overdue ? h("strong", {}, "Overdue") : "No") },
        { label: "Returned on", value: (o) => fmtDate(o.returned_on) },
        { label: "Amount due", value: (o) => fmtAmount(o.amount_due) },
        { label: "Actions", value: actions },
      ],
      load: (page) => get("/ill-outgoing", { page, page_size: 20, status: status.input.value, partner_id: partnerFilter.input.value, overdue: overdue.input.value }),
    });

    // new outgoing request
    const newPartner = field({ name: "partner_id", label: "Partner", options: recordOptions(partners.filter((p) => p.is_active), partnerLabel) });
    const newIsbn = field({ name: "isbn", label: "ISBN" });
    const create = form({
      fields: [newPartner, newIsbn],
      submit: "Create",
      label: "New outgoing request",
      async onSubmit(v) {
        create.fieldErrors({});
        ctx.clearMessages();
        let book;
        try {
          book = await findBook(v.isbn);
        } catch (error) {
          ctx.fail(error);
          return;
        }
        if (!v.partner_id) {
          newPartner.setError("Choose a partner.");
          return;
        }
        const created = await ctx.act(
          () => post("/ill-outgoing", { partner_id: Number(v.partner_id), book_id: book.id }),
          (o) => `Outgoing request ${o.id} created for ${book.title}.`,
          reload,
          (error) => create.fieldErrors(fieldProblems(error)),
        );
        if (created) newIsbn.input.value = "";
      },
    });

    const filters = form({
      fields: [status, partnerFilter, overdue],
      submit: "Filter",
      label: "Outgoing request filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    replace(ctx.body, section("New outgoing request", create), filters, panel, list.el);
    await list.goTo(1);
  },
};

// ---- LIB-UI-ILL-05 ---------------------------------------------------------------

const partnersScreen = {
  id: "ill-05",
  title: "Partners",
  module: MODULE,
  roles: ["librarian", "admin"],
  async render(ctx) {
    const editor = h("div", { class: "ill-panel" });
    const active = field({ name: "is_active", label: "Active", options: BOOLEAN_FILTER });
    const q = field({ name: "q", label: "Search", hint: "Code or name." });
    const closeEditor = () => replace(editor);

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Code", value: (p) => p.code },
        { label: "Name", value: (p) => p.name },
        { label: "E-mail", value: (p) => p.email },
        { label: "Request fee", value: (p) => fmtAmount(p.request_fee) },
        { label: "Daily late fee", value: (p) => fmtAmount(p.daily_late_fee) },
        { label: "Max outgoing", value: (p) => String(p.max_outgoing) },
        { label: "Active", value: (p) => fmtBool(p.is_active) },
        { label: "Open incoming", value: (p) => String(p.open_incoming) },
        { label: "Open outgoing", value: (p) => String(p.open_outgoing) },
        ...(ctx.isAdmin ? [{ label: "Actions", value: (p) => button("Edit", () => openEditor(p)) }] : []),
      ],
      load: (page) => get("/ill-partners", { page, page_size: 20, is_active: active.input.value, q: q.input.value.trim() }),
    });

    const filters = form({
      fields: [active, q],
      submit: "Filter",
      label: "Partner filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });

    function openEditor(partner) {
      const name = field({ name: "name", label: "Name", value: partner.name });
      const email = field({ name: "email", label: "E-mail", type: "email", value: partner.email });
      const requestFee = field({ name: "request_fee", label: "Request fee", inputmode: "decimal", value: partner.request_fee, hint: "0.00–50.00; applies to requests sent afterwards." });
      const lateFee = field({ name: "daily_late_fee", label: "Daily late fee", inputmode: "decimal", value: partner.daily_late_fee, hint: "0.00–10.00; applies to requests sent afterwards." });
      const maxOutgoing = field({ name: "max_outgoing", label: "Max outgoing", type: "number", min: 1, max: 20, value: String(partner.max_outgoing) });
      const isActive = field({ name: "is_active", label: "Active", options: ACTIVE_OPTIONS, value: String(partner.is_active) });
      const save = (v, node) =>
        ctx.act(
          () =>
            patch(`/ill-partners/${partner.id}`, {
              name: v.name.trim(),
              email: v.email.trim(),
              request_fee: v.request_fee.trim(),
              daily_late_fee: v.daily_late_fee.trim(),
              max_outgoing: Number(v.max_outgoing),
              is_active: v.is_active === "true",
            }),
          (p) => `Partner ${p.code} saved.`,
          async () => {
            closeEditor();
            await list.reload();
          },
          (error) => node.fieldErrors(fieldProblems(error)),
        );
      const node = form({
        fields: [name, email, requestFee, lateFee, maxOutgoing, isActive],
        submit: "Save",
        label: "Change partner",
        extra: button("Close", closeEditor),
        onSubmit(v) {
          node.fieldErrors({});
          if (partner.is_active && v.is_active === "false") {
            ctx.ask({ text: `Deactivate partner ${partner.code}? Requests already sent to it continue.`, onConfirm: () => save(v, node) });
          } else {
            return save(v, node);
          }
          return undefined;
        },
      });
      replace(editor, section(`Change partner ${partner.code}`, node));
    }

    let create = null;
    if (ctx.isAdmin) {
      const code = field({ name: "code", label: "Code", hint: "2–10 characters: A–Z and 0–9." });
      const name = field({ name: "name", label: "Name" });
      const email = field({ name: "email", label: "E-mail", type: "email" });
      const requestFee = field({ name: "request_fee", label: "Request fee", inputmode: "decimal", value: "0.00", hint: "0.00–50.00; charged to the member per request." });
      const lateFee = field({ name: "daily_late_fee", label: "Daily late fee", inputmode: "decimal", value: "0.00", hint: "0.00–10.00 per day." });
      const maxOutgoing = field({ name: "max_outgoing", label: "Max outgoing", type: "number", min: 1, max: 20, value: "5", hint: "1–20 open outgoing requests." });
      create = form({
        fields: [code, name, email, requestFee, lateFee, maxOutgoing],
        submit: "Create",
        label: "Create partner",
        async onSubmit(v) {
          create.fieldErrors({});
          const made = await ctx.act(
            () =>
              post("/ill-partners", {
                code: v.code.trim(),
                name: v.name.trim(),
                email: v.email.trim(),
                request_fee: v.request_fee.trim(),
                daily_late_fee: v.daily_late_fee.trim(),
                max_outgoing: Number(v.max_outgoing),
              }),
            (p) => `Partner ${p.code} created.`,
            () => list.reload(),
            (error) => {
              const problems = fieldProblems(error);
              if (error.code === "CONFLICT" && error.details?.field) problems[error.details.field] = error.message;
              create.fieldErrors(problems);
            },
          );
          if (made) {
            code.input.value = "";
            name.input.value = "";
            email.input.value = "";
          }
        },
      });
    }

    replace(ctx.body, create ? section("Create partner", create) : null, filters, editor, list.el);
    await list.goTo(1);
  },
};

// ---- LIB-UI-ILL-06 ---------------------------------------------------------------

const activityReportScreen = {
  id: "ill-06",
  title: "Interlibrary activity report",
  module: MODULE,
  roles: ["librarian", "admin"],
  async render(ctx) {
    const from = field({ name: "from", label: "From", type: "date", value: addDays(ctx.today, -29) });
    const to = field({ name: "to", label: "To", type: "date", value: ctx.today });
    const list = pagedTable({
      onError: (e) => {
        replace(list.el);
        ctx.fail(e);
      },
      columns: [
        { label: "Partner", value: (r) => r.partner_code },
        { label: "Sent", value: (r) => String(r.sent) },
        { label: "Rejected", value: (r) => String(r.rejected) },
        { label: "Received", value: (r) => String(r.received) },
        { label: "Late returns", value: (r) => String(r.late_returns) },
        { label: "Outgoing shipped", value: (r) => String(r.outgoing_shipped) },
        { label: "Outgoing returned", value: (r) => String(r.outgoing_returned) },
        { label: "Outgoing lost", value: (r) => String(r.outgoing_lost) },
        { label: "Amount due", value: (r) => fmtAmount(r.amount_due) },
      ],
      load: (page) => get("/reports/ill-activity", { from: from.input.value, to: to.input.value, page, page_size: 20 }),
    });
    const node = form({
      fields: [from, to],
      submit: "Show",
      label: "Interlibrary activity",
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

export const interlibraryScreens = [requestScreen, myRequestsScreen, incomingDeskScreen, outgoingDeskScreen, partnersScreen, activityReportScreen];
