// Modules 9 and 10: search and reports.

import { get } from "../api.js";
import {
  branchOptions,
  choices,
  field,
  fmtAmount,
  fmtDate,
  form,
  h,
  link,
  pagedTable,
  replace,
  table,
  words,
} from "../ui.js";
import { branchMap, branchName } from "../views.js";
import { authorNames, availabilityText } from "./catalog.js";

// ---- LIB-UI-SRCH-01 --------------------------------------------------------------

const searchScreen = {
  id: "srch-01",
  title: "Search",
  module: "Search",
  roles: ["all"],
  async render(ctx) {
    const map = await branchMap(ctx);
    const branches = await ctx.branches();
    const q = field({ name: "q", label: "Search text", hint: "Title, subtitle, author, publisher or ISBN." });
    const author = field({ name: "author", label: "Author" });
    const publisher = field({ name: "publisher", label: "Publisher" });
    const language = field({ name: "language", label: "Language", hint: "Two letters, for example tr." });
    const yearFrom = field({ name: "year_from", label: "Year from", type: "number" });
    const yearTo = field({ name: "year_to", label: "Year to", type: "number" });
    const classification = field({ name: "classification_prefix", label: "Classification prefix" });
    const available = field({
      name: "available_only",
      label: "Available only",
      options: [{ value: "false", label: "No" }, { value: "true", label: "Yes" }],
    });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      onRowClick: (r) => ctx.navigate(`#/cat-02/${r.book.id}`),
      columns: [
        { label: "Title", value: (r) => link(r.book.title, `#/cat-02/${r.book.id}`) },
        { label: "Authors", value: (r) => authorNames(r.book) },
        { label: "Year", value: (r) => String(r.book.publication_year) },
        { label: "Availability", value: (r) => availabilityText(r.book, map) },
      ],
      load: (page) =>
        get("/search/books", {
          page,
          page_size: 20,
          q: q.input.value.trim(),
          author: author.input.value.trim(),
          publisher: publisher.input.value.trim(),
          language: language.input.value.trim(),
          year_from: year_from(),
          year_to: year_to(),
          classification_prefix: classification.input.value.trim(),
          available_only: available.input.value,
          branch_id: branch.input.value,
        }),
    });
    const year_from = () => yearFrom.input.value.trim();
    const year_to = () => yearTo.input.value.trim();
    const results = h("div", { class: "results" });
    const node = form({
      fields: [q, author, publisher, language, yearFrom, yearTo, classification, available, branch],
      submit: "Search",
      label: "Search books",
      cls: "filters",
      async onSubmit() {
        ctx.clearMessages();
        replace(results, list.el);
        await list.goTo(1);
      },
    });
    replace(ctx.body, node, results);
  },
};

// ---- reports ---------------------------------------------------------------------

function addDays(isoDate, days) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

const reportScreen = ({ id, title, build }) => ({
  id,
  title,
  module: "Reports",
  roles: ["librarian", "admin"],
  async render(ctx) {
    await build(ctx);
  },
});

const mostBorrowed = reportScreen({
  id: "rep-01",
  title: "Most borrowed",
  async build(ctx) {
    const branches = await ctx.branches();
    const from = field({ name: "from", label: "From", type: "date", value: addDays(ctx.today, -29) });
    const to = field({ name: "to", label: "To", type: "date", value: ctx.today });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "All branches" }) });
    const limit = field({ name: "limit", label: "Limit", type: "number", value: "10", min: 1, max: 100 });
    const out = h("div", { class: "report" });
    const node = form({
      fields: [from, to, branch, limit],
      submit: "Show",
      label: "Most borrowed books",
      cls: "filters",
      async onSubmit(v) {
        ctx.clearMessages();
        try {
          const data = await get("/reports/most-borrowed", { from: v.from, to: v.to, branch_id: v.branch_id, limit: v.limit.trim() });
          replace(
            out,
            table({
              columns: [
                { label: "Rank", value: (r) => String(r.rank) },
                { label: "Title", value: (r) => link(r.title, `#/cat-02/${r.book_id}`) },
                { label: "ISBN", value: (r) => r.isbn },
                { label: "Loans", value: (r) => String(r.loan_count) },
              ],
              rows: data.items,
            }),
          );
        } catch (error) {
          replace(out);
          ctx.fail(error);
        }
      },
    });
    replace(ctx.body, node, out);
    node.requestSubmit();
  },
});

const overdueReport = reportScreen({
  id: "rep-02",
  title: "Overdue loans",
  async build(ctx) {
    const branches = await ctx.branches();
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "All branches" }) });
    const total = h("p", { class: "total" });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Loan", value: (r) => String(r.loan_id) },
        { label: "Member", value: (r) => link(`${r.member_no} ${r.member_name}`, `#/mem-03/${r.member_id}`) },
        { label: "Title", value: (r) => link(r.title, `#/cat-02/${r.book_id}`) },
        { label: "Barcode", value: (r) => r.copy_barcode },
        { label: "Due date", value: (r) => fmtDate(r.due_date) },
        { label: "Late days", value: (r) => String(r.late_days) },
        { label: "Accrued late fee", value: (r) => fmtAmount(r.accrued_late_fee) },
      ],
      load: async (page) => {
        const data = await get("/reports/overdue", { page, page_size: 20, branch_id: branch.input.value });
        replace(total, "Total accrued: ", h("strong", {}, fmtAmount(data.total_accrued)));
        return data;
      },
    });
    const node = form({
      fields: [branch],
      submit: "Show",
      label: "Overdue loans",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    replace(ctx.body, node, total, list.el);
    await list.goTo(1);
  },
});

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

const monthlySummary = reportScreen({
  id: "rep-03",
  title: "Monthly summary",
  async build(ctx) {
    const branches = await ctx.branches();
    const year = field({ name: "year", label: "Year", type: "number", value: ctx.today.slice(0, 4), min: 1900, max: 2100 });
    const month = field({
      name: "month",
      label: "Month",
      options: MONTHS.map((name, i) => ({ value: String(i + 1), label: name })),
      value: String(Number(ctx.today.slice(5, 7))),
    });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "All branches" }) });
    const out = h("div", { class: "report" });
    const rows = [
      ["New members", "new_members"],
      ["Loans created", "loans_created"],
      ["Loans returned", "loans_returned"],
      ["Loans lost", "loans_lost"],
      ["Reservations created", "reservations_created"],
      ["Reservations fulfilled", "reservations_fulfilled"],
      ["Reservations expired", "reservations_expired"],
      ["Fees created", "fees_created", true],
      ["Payments received", "payments_received", true],
      ["Fees waived", "fees_waived", true],
    ];
    const node = form({
      fields: [year, month, branch],
      submit: "Show",
      label: "Monthly summary",
      cls: "filters",
      async onSubmit(v) {
        ctx.clearMessages();
        try {
          const data = await get("/reports/monthly-summary", { year: v.year.trim(), month: v.month, branch_id: v.branch_id });
          replace(
            out,
            table({
              columns: [
                { label: "Figure", value: (r) => r[0] },
                { label: "Value", value: (r) => (r[2] ? fmtAmount(data[r[1]]) : String(data[r[1]])) },
              ],
              rows,
            }),
          );
        } catch (error) {
          replace(out);
          ctx.fail(error);
        }
      },
    });
    replace(ctx.body, node, out);
    node.requestSubmit();
  },
});

const copiesByStatus = reportScreen({
  id: "rep-04",
  title: "Copies by status",
  async build(ctx) {
    const branches = await ctx.branches();
    const map = await branchMap(ctx);
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "All branches" }) });
    const out = h("div", { class: "report" });
    const node = form({
      fields: [branch],
      submit: "Show",
      label: "Copies by status",
      cls: "filters",
      async onSubmit(v) {
        ctx.clearMessages();
        try {
          const data = await get("/reports/inventory", { branch_id: v.branch_id });
          replace(
            out,
            table({
              columns: [
                { label: "Branch", value: (r) => (r.branch_id === null ? "No branch (in transfer or lost)" : branchName(map, r.branch_id)) },
                { label: "Status", value: (r) => words(r.status) },
                { label: "Copies", value: (r) => String(r.copies) },
              ],
              rows: data.items,
            }),
          );
        } catch (error) {
          replace(out);
          ctx.fail(error);
        }
      },
    });
    replace(ctx.body, node, out);
    node.requestSubmit();
  },
});

export const discoveryScreens = [searchScreen, mostBorrowed, overdueReport, monthlySummary, copiesByStatus];
