// Module 29: printing and copying (LIB-UI-PRT-01 to LIB-UI-PRT-05).

import { fetchAll, get, patch, post } from "../api.js";
import { findMember } from "../context.js";
import {
  anyOption,
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
  pagedTable,
  replace,
  section,
  uid,
  words,
} from "../ui.js";
import { branchMap, branchName, memberLink, withMembers } from "../views.js";

const MODULE = "Printing and copying";
const JOB_STATUSES = ["queued", "printed", "cancelled", "expired", "failed"];
const PRINTER_STATUSES = ["active", "out_of_service", "retired"];
const YES_NO_FILTER = [anyOption(), { value: "true", label: "Yes" }, { value: "false", label: "No" }];

// ---- helpers ---------------------------------------------------------------------

/** A labelled checkbox that holds a boolean request field. */
function checkField({ name, label, checked = false, hint }) {
  const id = uid(name);
  const input = h("input", { id, name, type: "checkbox" });
  input.checked = checked;
  const errorBox = h("small", { class: "field-error", id: `${id}-error` });
  input.setAttribute("aria-describedby", errorBox.id);
  const wrap = h(
    "div",
    { class: "field check-field" },
    h("span", { class: "check" }, input, h("label", { for: id }, label)),
    hint ? h("small", { class: "hint" }, hint) : null,
    errorBox,
  );
  wrap.input = input;
  wrap.setError = (problem) => {
    errorBox.textContent = problem || "";
    if (problem) input.setAttribute("aria-invalid", "true");
    else input.removeAttribute("aria-invalid");
  };
  return wrap;
}

const printerLabel = (map, p) => `${p.code} – ${p.name} (${branchName(map, p.branch_id)})`;
const printerOptions = (map, printers, { any } = {}) => {
  const list = printers.map((p) => ({ value: p.id, label: printerLabel(map, p) }));
  return any === undefined ? list : [anyOption(any), ...list];
};

const money = (cents) => `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, "0")}`;

/** Sheets and expected cost of a job (LIB-PRT-17), from the free pages and pack pages left. */
export function estimate({ pages, copies, color, duplex }, { freeLeft, packLeft }) {
  const printed = pages * copies;
  const sheets = (duplex ? Math.ceil(pages / 2) : pages) * copies;
  if (color) return { sheets, cents: printed * 200 };
  const free = Math.min(printed, freeLeft);
  const pack = Math.min(printed - free, packLeft);
  return { sheets, cents: (printed - free - pack) * 50 };
}

const monthStart = (today) => `${today.slice(0, 8)}01`;

function jobColumns(map, { withMember = false, actions } = {}) {
  const columns = [{ label: "ID", value: (j) => String(j.id) }];
  if (withMember) columns.push({ label: "Member", value: (j) => (j._member ? memberLink(j._member) : `#${j.member_id}`) });
  columns.push(
    { label: "Title", value: (j) => j.title },
    { label: "Printer", value: (j) => `${j.printer.code} (${branchName(map, j.printer.branch_id)})` },
    { label: "Pages", value: (j) => String(j.pages) },
    { label: "Copies", value: (j) => String(j.copies) },
    { label: "Sheets", value: (j) => String(j.sheets) },
    { label: "Color", value: (j) => fmtBool(j.color) },
    { label: "Duplex", value: (j) => fmtBool(j.duplex) },
    { label: "Status", value: (j) => j.status },
    { label: "Amount", value: (j) => fmtAmount(j.amount) },
    { label: "Submitted", value: (j) => fmtDateTime(j.submitted_at) },
    { label: "Released", value: (j) => fmtDateTime(j.released_at) },
  );
  if (actions) columns.push({ label: "Actions", value: (j) => actions(j) });
  return columns;
}

function quotaFacts(q) {
  return definitionList([
    ["Month", q.month],
    ["Membership type", words(q.membership_type)],
    ["Free pages", String(q.free_pages)],
    ["Free pages used", String(q.free_pages_used)],
    ["Free pages left", String(q.free_pages_left)],
    ["Pack pages left", String(q.pack_pages_left)],
    ["Pages printed", String(q.pages_printed)],
    ["Amount charged", fmtAmount(q.amount_charged)],
  ]);
}

// ---- LIB-UI-PRT-01 ---------------------------------------------------------------

const printScreen = {
  id: "prt-01",
  title: "Print",
  module: MODULE,
  roles: ["member"],
  async render(ctx) {
    const me = await get("/members/me");
    const map = await branchMap(ctx);
    const printers = await fetchAll("/printers", { status: "active" });
    let quota = null;

    const printer = field({ name: "printer_id", label: "Printer", options: printerOptions(map, printers) });
    const title = field({ name: "title", label: "Title", attrs: { maxlength: "100" } });
    const pages = field({ name: "pages", label: "Pages", type: "number", min: 1, max: 500, value: "1", hint: "1 to 500 pages of the document." });
    const copies = field({ name: "copies", label: "Copies", type: "number", min: 1, max: 20, value: "1", hint: "1 to 20 copies." });
    const color = checkField({ name: "color", label: "Color" });
    const duplex = checkField({ name: "duplex", label: "Duplex" });
    const preview = h("p", { class: "print-preview", "aria-live": "polite" });
    const facts = h("div", { class: "print-quota" });

    function drawPreview() {
      const p = Number(pages.input.value);
      const c = Number(copies.input.value);
      if (!quota || !Number.isInteger(p) || !Number.isInteger(c) || p < 1 || c < 1) {
        replace(preview, "Sheets: – · Expected cost: –");
        return;
      }
      const e = estimate(
        { pages: p, copies: c, color: color.input.checked, duplex: duplex.input.checked },
        { freeLeft: quota.free_pages_left, packLeft: quota.pack_pages_left },
      );
      replace(preview, `Sheets: ${e.sheets} · Expected cost: ${fmtAmount(money(e.cents))}`);
    }

    async function loadQuota() {
      quota = await get(`/members/${me.id}/print-quota`);
      replace(
        facts,
        definitionList([
          ["Free pages left", String(quota.free_pages_left)],
          ["Pack pages left", String(quota.pack_pages_left)],
        ]),
      );
      drawPreview();
    }

    const queued = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: jobColumns(map, {
        actions: (j) =>
          h(
            "span",
            { class: "row-actions" },
            button("Release", () => ctx.act(() => post(`/print-jobs/${j.id}/release`), `Print job ${j.id} printed.`, reloadAll)),
            button("Cancel", () =>
              ctx.ask({
                text: `Cancel print job "${j.title}"?`,
                onConfirm: () => ctx.act(() => post(`/print-jobs/${j.id}/cancel`), `Print job ${j.id} cancelled.`, reloadAll),
              }),
            ),
          ),
      }),
      load: (page) => get(`/members/${me.id}/print-jobs`, { page, page_size: 20, status: "queued" }),
    });

    async function reloadAll() {
      await Promise.all([loadQuota(), queued.reload()]);
    }

    const node = form({
      fields: [printer, title, pages, copies, color, duplex],
      submit: "Send",
      label: "Send a print job",
      extra: preview,
      async onSubmit(v) {
        node.fieldErrors({});
        await ctx.act(
          () =>
            post("/print-jobs", {
              printer_id: int(v.printer_id),
              title: v.title.trim(),
              pages: int(v.pages),
              copies: int(v.copies),
              color: v.color,
              duplex: v.duplex,
            }),
          (j) => `Print job ${j.id} sent (${j.sheets} sheets).`,
          reloadAll,
          (error) => node.fieldErrors(fieldProblems(error)),
        );
      },
    });
    node.addEventListener("input", drawPreview);
    node.addEventListener("change", drawPreview);

    replace(
      ctx.body,
      section("Send a print job", node),
      section("My free pages and packs", facts),
      section("My queued jobs", queued.el),
    );
    await Promise.all([loadQuota(), queued.goTo(1)]);
  },
};

// ---- LIB-UI-PRT-02 ---------------------------------------------------------------

const myPrintingScreen = {
  id: "prt-02",
  title: "My printing",
  module: MODULE,
  roles: ["member"],
  async render(ctx) {
    const me = await get("/members/me");
    const map = await branchMap(ctx);

    const status = field({ name: "status", label: "Status", options: choices(JOB_STATUSES, { any: "Any" }) });
    const jobs = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: jobColumns(map),
      load: (page) => get(`/members/${me.id}/print-jobs`, { page, page_size: 20, status: status.input.value }),
    });
    const filters = form({
      fields: [status],
      submit: "Show",
      label: "Job filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        jobs.goTo(1);
      },
    });

    const packs = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Bought on", value: (p) => fmtDate(p.bought_on) },
        { label: "Pages", value: (p) => String(p.pages) },
        { label: "Pages left", value: (p) => String(p.pages_left) },
        { label: "Fee", value: (p) => fmtText(p.fee_id) },
      ],
      load: (page) => get(`/members/${me.id}/print-packs`, { page, page_size: 20 }),
    });

    const month = field({ name: "month", label: "Month", type: "month", value: ctx.today.slice(0, 7) });
    const quotaBox = h("div", { class: "quota-box" });
    async function showQuota() {
      try {
        const q = await get(`/members/${me.id}/print-quota`, { month: month.input.value });
        replace(quotaBox, quotaFacts(q));
      } catch (error) {
        replace(quotaBox);
        ctx.fail(error);
      }
    }
    const quotaForm = form({
      fields: [month],
      submit: "Show quota",
      label: "Quota of a month",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return showQuota();
      },
    });

    replace(
      ctx.body,
      section("Quota", quotaForm, quotaBox),
      section("My print jobs", filters, jobs.el),
      section("My page packs", packs.el),
    );
    await Promise.all([jobs.goTo(1), packs.goTo(1), showQuota()]);
  },
};

// ---- LIB-UI-PRT-03 ---------------------------------------------------------------

const printersScreen = {
  id: "prt-03",
  title: "Printers",
  module: MODULE,
  roles: ["all"],
  async render(ctx) {
    const branches = await ctx.branches();
    const map = await branchMap(ctx);
    const editBox = h("div", { class: "printer-edit" });
    const refillBox = h("div", { class: "printer-refill" });
    const createBox = h("div", { class: "printer-create" });

    // filters
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const status = field({ name: "status", label: "Status", options: choices(PRINTER_STATUSES, { any: "Any" }) });
    const colorFilter = field({ name: "color", label: "Color", options: YES_NO_FILTER });
    const lowPaper = field({ name: "low_paper", label: "Low paper", options: YES_NO_FILTER });

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      rowClass: (p) => (p.low_paper && p.status !== "retired" ? "low-paper" : undefined),
      columns: [
        { label: "Code", value: (p) => p.code },
        { label: "Name", value: (p) => p.name },
        { label: "Branch", value: (p) => branchName(map, p.branch_id) },
        { label: "Color", value: (p) => fmtBool(p.color) },
        { label: "Duplex", value: (p) => fmtBool(p.duplex) },
        {
          label: "Paper left",
          value: (p) =>
            h("span", {}, String(p.paper_left), p.low_paper ? [" ", h("strong", { class: "low-paper-mark" }, "Low paper")] : null),
        },
        { label: "Status", value: (p) => words(p.status) },
        ...(ctx.isAdmin
          ? [{ label: "Actions", value: (p) => (p.status === "retired" ? "–" : button("Edit", () => showEdit(p))) }]
          : []),
      ],
      load: async (page) => {
        const data = await get("/printers", {
          page,
          page_size: 20,
          branch_id: branch.input.value,
          status: status.input.value,
          color: colorFilter.input.value,
          low_paper: lowPaper.input.value,
        });
        return data;
      },
    });

    async function reloadAll() {
      await list.reload();
      if (ctx.isStaff) await drawRefill();
    }

    const filters = form({
      fields: [branch, status, colorFilter, lowPaper],
      submit: "Show",
      label: "Printer filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });

    // refill (librarian and admin)
    async function drawRefill() {
      const all = await fetchAll("/printers");
      const usable = all.filter((p) => p.status !== "retired");
      const printer = field({ name: "printer_id", label: "Printer", options: printerOptions(map, usable) });
      const sheets = field({ name: "sheets", label: "Sheets", type: "number", min: 1, max: 5000, hint: "1 to 5000 sheets; a printer holds at most 5000." });
      const node = form({
        fields: [printer, sheets],
        submit: "Refill",
        label: "Refill a printer",
        async onSubmit(v) {
          node.fieldErrors({});
          await ctx.act(
            () => post(`/printers/${int(v.printer_id)}/refill`, { sheets: int(v.sheets) }),
            (p) => `Printer ${p.code} refilled: ${p.paper_left} sheets left.`,
            reloadAll,
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      replace(refillBox, section("Refill paper", node));
    }

    // create (admin)
    function drawCreate() {
      const b = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { activeOnly: true }) });
      const code = field({ name: "code", label: "Code", hint: "PR- and 3 digits, for example PR-001.", attrs: { maxlength: "6" } });
      const name = field({ name: "name", label: "Name", attrs: { maxlength: "200" } });
      const color = checkField({ name: "color", label: "Color" });
      const duplex = checkField({ name: "duplex", label: "Duplex" });
      const node = form({
        fields: [b, code, name, color, duplex],
        submit: "Create",
        label: "Create a printer",
        async onSubmit(v) {
          node.fieldErrors({});
          const created = await ctx.act(
            () =>
              post("/printers", {
                branch_id: int(v.branch_id),
                code: v.code.trim(),
                name: v.name.trim(),
                color: v.color,
                duplex: v.duplex,
              }),
            (p) => `Printer ${p.code} created.`,
            reloadAll,
            (error) => node.fieldErrors(fieldProblems(error)),
          );
          if (created) {
            code.input.value = "";
            name.input.value = "";
          }
        },
      });
      replace(createBox, section("Create a printer", node));
    }

    // change (admin)
    function showEdit(p) {
      const name = field({ name: "name", label: "Name", value: p.name, attrs: { maxlength: "200" } });
      const color = checkField({ name: "color", label: "Color", checked: p.color });
      const duplex = checkField({ name: "duplex", label: "Duplex", checked: p.duplex });
      const state = field({ name: "status", label: "Status", options: choices(PRINTER_STATUSES), value: p.status });
      const node = form({
        fields: [name, color, duplex, state],
        submit: "Save",
        label: `Change printer ${p.code}`,
        extra: button("Close", () => replace(editBox)),
        async onSubmit(v) {
          node.fieldErrors({});
          const body = { name: v.name.trim(), color: v.color, duplex: v.duplex, status: v.status };
          const save = () =>
            ctx.act(
              () => patch(`/printers/${p.id}`, body),
              (x) => `Printer ${x.code} saved.`,
              async () => {
                replace(editBox);
                await reloadAll();
              },
              (error) => node.fieldErrors(fieldProblems(error)),
            );
          const closing = v.status !== "active" && v.status !== p.status;
          const losing = (p.color && !v.color) || (p.duplex && !v.duplex);
          if (closing || losing) {
            ctx.ask({
              text: closing
                ? `Set printer ${p.code} to ${words(v.status)}? Its queued print jobs will be cancelled and the members notified.`
                : `Save the change? Queued print jobs of printer ${p.code} that need color or duplex will be cancelled and the members notified.`,
              onConfirm: save,
            });
          } else {
            await save();
          }
        },
      });
      replace(editBox, section(`Change printer ${p.code}`, node));
      editBox.scrollIntoView?.({ block: "nearest" });
    }

    replace(
      ctx.body,
      section("Printers", filters, list.el),
      editBox,
      ctx.isStaff ? refillBox : null,
      ctx.isAdmin ? createBox : null,
    );
    if (ctx.isAdmin) drawCreate();
    await Promise.all([list.goTo(1), ctx.isStaff ? drawRefill() : null]);
  },
};

// ---- LIB-UI-PRT-04 ---------------------------------------------------------------

const deskScreen = {
  id: "prt-04",
  title: "Print desk",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const map = await branchMap(ctx);
    const printers = await fetchAll("/printers");
    const usable = printers.filter((p) => p.status === "active");
    const cardBox = h("div", { class: "card-release-result" });

    // jobs with filters
    const fMember = field({ name: "member_no", label: "Member number", hint: "Leave empty for all members." });
    const fStatus = field({ name: "status", label: "Status", options: choices(JOB_STATUSES, { any: "Any" }) });
    const fPrinter = field({ name: "printer_id", label: "Printer", options: printerOptions(map, printers, { any: "Any" }) });
    const fBranch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const fFrom = field({ name: "from", label: "From", type: "date" });
    const fTo = field({ name: "to", label: "To", type: "date" });

    const jobActions = (j) => {
      if (j.status === "queued") {
        return h(
          "span",
          { class: "row-actions" },
          button("Release", () => ctx.act(() => post(`/print-jobs/${j.id}/release`), `Print job ${j.id} printed.`, () => list.reload())),
          button("Cancel", () =>
            ctx.ask({
              text: `Cancel print job "${j.title}"?`,
              onConfirm: () => ctx.act(() => post(`/print-jobs/${j.id}/cancel`), `Print job ${j.id} cancelled.`, () => list.reload()),
            }),
          ),
        );
      }
      if (j.status === "printed") {
        const reason = field({ name: "reason", label: "Reason", hint: "5–200 characters." });
        const wrap = h("form", { class: "inline-fail", novalidate: true }, reason, h("button", { type: "submit" }, "Fail"));
        wrap.addEventListener("submit", (event) => {
          event.preventDefault();
          ctx.act(
            () => post(`/print-jobs/${j.id}/fail`, { reason: reason.input.value.trim() }),
            `Print job ${j.id} recorded as failed and refunded.`,
            () => list.reload(),
          );
        });
        return wrap;
      }
      return "–";
    };

    let filterMember = null;
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: jobColumns(map, { withMember: true, actions: jobActions }),
      load: async (page) => {
        const data = await get("/print-jobs", {
          page,
          page_size: 20,
          member_id: filterMember ? filterMember.id : "",
          status: fStatus.input.value,
          printer_id: fPrinter.input.value,
          branch_id: fBranch.input.value,
          from: fFrom.input.value,
          to: fTo.input.value,
        });
        await withMembers(ctx, data.items);
        return data;
      },
    });
    const filters = form({
      fields: [fMember, fStatus, fPrinter, fBranch, fFrom, fTo],
      submit: "Show",
      label: "Job filters",
      cls: "filters",
      async onSubmit(v) {
        ctx.clearMessages();
        try {
          filterMember = v.member_no.trim() ? await findMember(v.member_no) : null;
        } catch (error) {
          ctx.fail(error);
          return;
        }
        await list.goTo(1);
      },
    });

    // send a job for a member
    const sMember = field({ name: "member_no", label: "Member number", hint: "For example M000001." });
    const sPrinter = field({ name: "printer_id", label: "Printer", options: printerOptions(map, usable) });
    const sTitle = field({ name: "title", label: "Title", attrs: { maxlength: "100" } });
    const sPages = field({ name: "pages", label: "Pages", type: "number", min: 1, max: 500, value: "1" });
    const sCopies = field({ name: "copies", label: "Copies", type: "number", min: 1, max: 20, value: "1" });
    const sColor = checkField({ name: "color", label: "Color" });
    const sDuplex = checkField({ name: "duplex", label: "Duplex" });
    const send = form({
      fields: [sMember, sPrinter, sTitle, sPages, sCopies, sColor, sDuplex],
      submit: "Send",
      label: "Send a print job for a member",
      async onSubmit(v) {
        send.fieldErrors({});
        await ctx.act(
          async () => {
            const member = await findMember(v.member_no);
            return post("/print-jobs", {
              member_id: member.id,
              printer_id: int(v.printer_id),
              title: v.title.trim(),
              pages: int(v.pages),
              copies: int(v.copies),
              color: v.color,
              duplex: v.duplex,
            });
          },
          (j) => `Print job ${j.id} sent (${j.sheets} sheets).`,
          () => list.reload(),
          (error) => send.fieldErrors(fieldProblems(error)),
        );
      },
    });

    // release by card
    const cPrinter = field({ name: "printer_id", label: "Printer", options: printerOptions(map, usable) });
    const cCard = field({ name: "card_no", label: "Card number", hint: "For example LC00000001.", attrs: { autocomplete: "off" } });
    const byCard = form({
      fields: [cPrinter, cCard],
      submit: "Release by card",
      label: "Release by card",
      async onSubmit(v) {
        byCard.fieldErrors({});
        replace(cardBox);
        const done = await ctx.act(
          () => post("/print-jobs/release-by-card", { printer_id: int(v.printer_id), card_no: v.card_no.trim() }),
          (r) => `Released ${r.released.length} job(s); refused ${r.refused.length}.`,
          () => list.reload(),
          (error) => byCard.fieldErrors(fieldProblems(error)),
        );
        if (done) {
          cCard.input.value = "";
          replace(
            cardBox,
            done.refused.length
              ? h(
                  "div",
                  {},
                  h("p", {}, "Refused jobs:"),
                  h("ul", { class: "refused" }, done.refused.map((r) => h("li", {}, `Job ${r.job_id}: `, h("strong", {}, r.code)))),
                )
              : null,
          );
        }
      },
    });

    // buy a pack
    const pMember = field({ name: "member_no", label: "Member number", hint: "For example M000001." });
    const pack = form({
      fields: [pMember],
      submit: "Buy pack",
      label: "Sell a page pack",
      async onSubmit(v) {
        pack.fieldErrors({});
        await ctx.act(
          async () => {
            const member = await findMember(v.member_no);
            return post(`/members/${member.id}/print-packs`);
          },
          (p) => `Page pack of ${p.pages} pages sold; fee ${p.fee_id}.`,
          () => list.reload(),
          (error) => pack.fieldErrors(fieldProblems(error)),
        );
      },
    });

    // process
    const processBox = h(
      "div",
      { class: "actions" },
      button("Process", () =>
        ctx.act(() => post("/printing/process"), (r) => `Expired print jobs: ${r.jobs_expired}.`, () => list.reload()),
      ),
    );

    replace(
      ctx.body,
      section("Print jobs", filters, list.el),
      section("Send a print job for a member", send),
      section("Release by card", h("p", { class: "hint" }, "Releases the queued jobs of the card's member at the printer."), byCard, cardBox),
      section("Page packs", h("p", { class: "hint" }, "A pack of 50 black-and-white pages costs 20.00 TL."), pack),
      section("Old jobs", h("p", { class: "hint" }, "Queued jobs older than 24 hours expire."), processBox),
    );
    await list.goTo(1);
  },
};

// ---- LIB-UI-PRT-05 ---------------------------------------------------------------

const reportScreen = {
  id: "prt-05",
  title: "Printing report",
  module: MODULE,
  roles: ["librarian", "admin"],
  async render(ctx) {
    const branches = await ctx.branches();
    const map = await branchMap(ctx);
    const from = field({ name: "from", label: "From", type: "date", value: monthStart(ctx.today) });
    const to = field({ name: "to", label: "To", type: "date", value: ctx.today });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "All branches" }) });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Branch", value: (r) => branchName(map, r.branch_id) },
        { label: "Jobs printed", value: (r) => String(r.jobs_printed) },
        { label: "Pages", value: (r) => String(r.pages) },
        { label: "Color pages", value: (r) => String(r.color_pages) },
        { label: "Sheets", value: (r) => String(r.sheets) },
        { label: "Free pages", value: (r) => String(r.free_pages) },
        { label: "Pack pages", value: (r) => String(r.pack_pages) },
        { label: "Charged pages", value: (r) => String(r.charged_pages) },
        { label: "Revenue", value: (r) => fmtAmount(r.revenue) },
        { label: "Packs sold", value: (r) => String(r.packs_sold) },
        { label: "Jobs failed", value: (r) => String(r.jobs_failed) },
        { label: "Refunds pending", value: (r) => fmtAmount(r.refunds_pending) },
      ],
      load: (page) => get("/reports/printing", { page, page_size: 50, from: from.input.value, to: to.input.value, branch_id: branch.input.value }),
    });
    const node = form({
      fields: [from, to, branch],
      submit: "Show",
      label: "Printing report",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    replace(ctx.body, section("Printing per branch", node, list.el));
    await list.goTo(1);
  },
};

export const printingScreens = [printScreen, myPrintingScreen, printersScreen, deskScreen, reportScreen];
