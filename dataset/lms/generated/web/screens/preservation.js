// Module 23: preservation (budgets, inspection, repair jobs, shipments, reports, repairs on the book page).

import { api, clientError, fetchAll, get, patch, post } from "../api.js";
import { bookPageParts } from "../registry.js";
import {
  branchOptions,
  button,
  choices,
  definitionList,
  dash,
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
  pagedTable,
  recordOptions,
  replace,
  section,
  table,
  words,
} from "../ui.js";
import { branchMap, branchName } from "../views.js";

const CONDITIONS = ["good", "worn", "fragile"];
const KINDS = ["repair", "rebinding", "conservation"];
const PROVIDERS = ["in_house", "supplier"];
const PRIORITIES = ["normal", "urgent"];
const JOB_STATUSES = ["requested", "approved", "sent", "returned", "cancelled", "lost"];
const OUTCOMES = ["repaired", "unrepairable"];
const APPROVAL_LIMIT_CENTS = 50000; // LIB-PRE-13: above 500.00 only an admin approves

// ---- helpers ---------------------------------------------------------------------

const yearOf = (ctx) => Number(ctx.today.slice(0, 4));

/** "12.5" → 1250; null when the text is not an amount. */
function toCents(value) {
  const match = /^([+-]?)(\d+)(?:\.(\d{1,2}))?$/.exec(String(value ?? "").trim());
  if (!match) return null;
  const cents = Number(match[2]) * 100 + Number((match[3] || "").padEnd(2, "0") || 0);
  return match[1] === "-" ? -cents : cents;
}

function fromCents(cents) {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}

async function copyByBarcode(barcode) {
  const wanted = String(barcode ?? "").trim();
  if (!wanted) {
    throw clientError("VALIDATION_ERROR", "Enter a barcode.", { fields: [{ field: "barcode", problem: "field required" }] });
  }
  return get(`/copies/by-barcode/${encodeURIComponent(wanted)}`);
}

/** A 422 about `copy_id` belongs to the field `barcode`. */
function problemsOf(error) {
  const problems = fieldProblems(error);
  if (problems.copy_id && !problems.barcode) problems.barcode = problems.copy_id;
  if (problems.body && /supplier_id/.test(problems.body) && !problems.supplier_id) problems.supplier_id = problems.body;
  return problems;
}

const supplierName = (suppliers, id) => (id === null || id === undefined ? dash : suppliers.find((s) => s.id === id)?.name || `#${id}`);

function yearField(ctx, value, label = "Year") {
  return field({ name: "year", label, type: "number", min: 2000, max: 2100, value: value ?? yearOf(ctx) });
}

// ---- LIB-UI-PRE-01 ---------------------------------------------------------------

const budgetsScreen = {
  id: "pre-01",
  title: "Budgets",
  module: "Preservation",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const out = h("div", { class: "budget-table" });
    const year = yearField(ctx);
    let shown = yearOf(ctx);

    async function load() {
      const wanted = int(year.input.value);
      if (typeof wanted !== "number") {
        ctx.fail(clientError("VALIDATION_ERROR", "Enter a year between 2000 and 2100.", { fields: [{ field: "year", problem: "must be a whole number" }] }));
        return;
      }
      let rows;
      try {
        rows = await Promise.all(
          branches.map(async (branch) => {
            try {
              return { branch, budget: await get(`/preservation-budgets/${branch.id}/${wanted}`) };
            } catch (error) {
              if (error.status === 404 && error.code === "NOT_FOUND") return { branch, budget: null };
              throw error;
            }
          }),
        );
      } catch (error) {
        replace(out);
        ctx.fail(error);
        return;
      }
      shown = wanted;
      const columns = [
        { label: "Branch", value: (r) => `${r.branch.code} – ${r.branch.name}` },
        { label: "Budget", value: (r) => (r.budget ? fmtAmount(r.budget.amount) : "No budget") },
        { label: "Committed", value: (r) => (r.budget ? fmtAmount(r.budget.committed) : dash) },
        { label: "Spent", value: (r) => (r.budget ? fmtAmount(r.budget.spent) : dash) },
        { label: "Available", value: (r) => (r.budget ? fmtAmount(r.budget.available) : dash) },
      ];
      if (ctx.isAdmin) columns.push({ label: "Set budget", value: (r) => setForm(r) });
      replace(out, table({ columns, rows, caption: `Preservation budgets ${wanted}`, rowClass: (r) => (r.budget && toCents(r.budget.available) < 0 ? "overdue" : undefined) }));
    }

    function setForm(row) {
      const amount = field({ name: "amount", label: `Budget of ${row.branch.code}`, inputmode: "decimal", value: row.budget ? row.budget.amount : "", hint: "0.00–1000000.00" });
      const node = form({
        fields: [amount],
        submit: "Set budget",
        label: `Set budget ${row.branch.code}`,
        cls: "budget-set-form",
        async onSubmit(v) {
          node.fieldErrors({});
          await ctx.act(
            () => api("PUT", `/preservation-budgets/${row.branch.id}/${shown}`, { body: { amount: v.amount.trim() } }),
            (r) => `Budget of ${row.branch.code} for ${r.year} set to ${fmtAmount(r.amount)}.`,
            load,
            (error) => node.fieldErrors(problemsOf(error)),
          );
        },
      });
      return node;
    }

    const filter = form({
      fields: [year],
      submit: "Show",
      label: "Choose a year",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return load();
      },
    });
    replace(ctx.body, section("Yearly budgets", filter, out));
    await load();
  },
};

// ---- LIB-UI-PRE-02 --------------------------------------------------------------

const inspectionScreen = {
  id: "pre-02",
  title: "Inspection",
  module: "Preservation",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const detail = h("div", { class: "copy-detail" });
    const inspectBox = h("div", { class: "inspect-box" });
    const historyBox = h("div", { class: "inspection-history" });
    let current = null;

    async function openCopy(copy) {
      current = copy;
      const book = await ctx.book(copy.book_id);
      const map = await branchMap(ctx);
      replace(
        detail,
        definitionList([
          ["Barcode", copy.barcode],
          ["Title", link(book.title, `#/cat-02/${book.id}`)],
          ["Status", words(copy.status)],
          ["Condition", copy.condition],
          ["Current branch", branchName(map, copy.current_branch_id)],
          ["Open repair job", copy.open_job_id === null ? "None" : link(`#${copy.open_job_id}`, "#/pre-03")],
        ]),
      );
      const condition = field({ name: "condition", label: "Condition", options: choices(CONDITIONS), value: copy.condition });
      const note = field({ name: "note", label: "Note", type: "textarea", hint: "At most 500 characters." });
      const node = form({
        fields: [condition, note],
        submit: "Record",
        label: "Record inspection",
        async onSubmit(v) {
          node.fieldErrors({});
          await ctx.act(
            () => post(`/copies/${current.id}/inspections`, { condition: v.condition, note: v.note }),
            (r) => `Inspection recorded: copy ${current.barcode} is ${r.condition}.`,
            async () => openCopy(await get(`/copies/${current.id}`)),
            (error) => node.fieldErrors(problemsOf(error)),
          );
        },
      });
      replace(inspectBox, section("Record inspection", node));
      const history = pagedTable({
        onError: (e) => ctx.fail(e),
        columns: [
          { label: "Inspected at", value: (i) => fmtDateTime(i.inspected_at) },
          { label: "Condition", value: (i) => i.condition },
          { label: "Note", value: (i) => fmtText(i.note) },
          { label: "Inspected by", value: (i) => `#${i.inspected_by}` },
        ],
        load: (page) => get(`/copies/${copy.id}/inspections`, { page, page_size: 10 }),
      });
      replace(historyBox, section("Inspection history", history.el));
      await history.goTo(1);
    }

    const barcode = field({ name: "barcode", label: "Barcode", hint: "Scan or type the barcode of the copy." });
    const lookup = form({
      fields: [barcode],
      submit: "Find copy",
      label: "Choose a copy",
      async onSubmit(v) {
        ctx.clearMessages();
        try {
          await openCopy(await copyByBarcode(v.barcode));
        } catch (error) {
          replace(detail);
          replace(inspectBox);
          replace(historyBox);
          ctx.fail(error);
        }
      },
    });
    replace(ctx.body, section("Copy", lookup, detail), inspectBox, historyBox);
    barcode.input.focus();
    if (/^\d+$/.test(ctx.param || "")) {
      try {
        const copy = await get(`/copies/${ctx.param}`);
        barcode.input.value = copy.barcode;
        await openCopy(copy);
      } catch (error) {
        ctx.fail(error);
      }
    }
  },
};

// ---- LIB-UI-PRE-03 --------------------------------------------------------------

const jobsScreen = {
  id: "pre-03",
  title: "Jobs",
  module: "Preservation",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const map = await branchMap(ctx);
    const branches = await ctx.branches();
    const suppliers = await fetchAll("/suppliers");
    const supplierOptions = (includeAny, current) => [
      includeAny ? { value: "", label: "Any" } : { value: "", label: "None (in-house)" },
      ...recordOptions(suppliers.filter((s) => s.is_active || s.id === current), (s) => s.name),
    ];
    const editor = h("div", { class: "job-editor" });
    const suggestionsBox = h("div", { class: "suggestions" });
    let copyFilter = "";

    const reloadAll = async () => {
      replace(editor);
      await Promise.all([list.reload(), loadSuggestions()]);
    };

    // ---- process
    const processBar = h(
      "div",
      { class: "actions" },
      button("Process", () =>
        ctx.act(
          () => post("/preservation/process"),
          (r) => `Processed. Overdue jobs: ${r.overdue}. Newly overdue: ${r.newly_overdue}. Expired requests: ${r.expired_requests}.`,
          reloadAll,
        ),
      ),
    );

    // ---- suggestions
    const sBranch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { activeOnly: true }) });
    async function loadSuggestions() {
      if (!sBranch.input.value) return;
      let data;
      try {
        data = await get("/preservation/suggestions", { branch_id: sBranch.input.value });
      } catch (error) {
        replace(suggestionsBox);
        ctx.fail(error);
        return;
      }
      replace(
        suggestionsBox,
        table({
          caption: "Copies that need a job",
          columns: [
            { label: "Barcode", value: (s) => s.barcode },
            { label: "Reason", value: (s) => words(s.reason) },
            {
              label: "Actions",
              value: (s) =>
                button("Create job", () => {
                  cBarcode.input.value = s.barcode;
                  cKind.input.focus();
                  cKind.scrollIntoView?.({ block: "nearest" });
                }),
            },
          ],
          rows: data.items,
        }),
      );
    }
    const suggestForm = form({
      fields: [sBranch],
      submit: "Show suggestions",
      label: "Suggestions of a branch",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return loadSuggestions();
      },
    });
    sBranch.input.addEventListener("change", () => loadSuggestions());

    // ---- create
    const cBarcode = field({ name: "barcode", label: "Barcode" });
    const cKind = field({ name: "kind", label: "Kind", options: choices(KINDS) });
    const cProvider = field({ name: "provider", label: "Provider", options: choices(PROVIDERS) });
    const cSupplier = field({ name: "supplier_id", label: "Supplier", options: supplierOptions(false), hint: "Required for a supplier job." });
    const cPriority = field({ name: "priority", label: "Priority", options: choices(PRIORITIES) });
    const cCost = field({ name: "estimated_cost", label: "Estimated cost", inputmode: "decimal", value: "0.00", hint: "0.00–100000.00 TL" });
    const cNote = field({ name: "note", label: "Note", type: "textarea", hint: "At most 500 characters." });
    const create = form({
      fields: [cBarcode, cKind, cProvider, cSupplier, cPriority, cCost, cNote],
      submit: "Create",
      label: "Create job",
      async onSubmit(v) {
        create.fieldErrors({});
        let copy;
        try {
          copy = await copyByBarcode(v.barcode);
        } catch (error) {
          ctx.fail(error);
          create.fieldErrors(problemsOf(error));
          return;
        }
        const done = await ctx.act(
          () =>
            post("/repair-jobs", {
              copy_id: copy.id,
              kind: v.kind,
              provider: v.provider,
              supplier_id: int(v.supplier_id),
              priority: v.priority,
              estimated_cost: v.estimated_cost.trim(),
              note: v.note,
            }),
          (r) => `Job ${r.id} created for copy ${r.barcode} (${r.status}).`,
          reloadAll,
          (error) => create.fieldErrors(problemsOf(error)),
        );
        if (done) {
          cBarcode.input.value = "";
          cNote.input.value = "";
        }
      },
    });

    // ---- job actions
    function askApprove(job) {
      return (async () => {
        const y = yearOf(ctx);
        let budget = null;
        try {
          budget = await get(`/preservation-budgets/${job.branch_id}/${y}`);
        } catch (error) {
          if (!(error.status === 404 && error.code === "NOT_FOUND")) {
            ctx.fail(error);
            return;
          }
        }
        const lines = [];
        if (budget) {
          const available = toCents(budget.available);
          const amount = toCents(budget.amount);
          const limit = job.priority === "urgent" ? available + Math.floor(amount / 10) : available;
          lines.push(
            definitionList([
              [`Budget ${y}`, fmtAmount(budget.amount)],
              ["Committed", fmtAmount(budget.committed)],
              ["Spent", fmtAmount(budget.spent)],
              ["Available", fmtAmount(budget.available)],
              [job.priority === "urgent" ? "Limit for an urgent job" : "Limit for a normal job", fmtAmount(fromCents(limit))],
              ["Estimated cost of this job", fmtAmount(job.estimated_cost)],
            ]),
          );
        } else {
          lines.push(h("p", {}, `No budget is set for ${branchName(map, job.branch_id)} in ${y}; the job cannot be approved.`));
        }
        if (!ctx.isAdmin && (toCents(job.estimated_cost) ?? 0) > APPROVAL_LIMIT_CENTS) {
          lines.push(h("p", { role: "note" }, "A job above 500.00 TL can only be approved by an admin."));
        }
        ctx.ask({
          text: `Approve job ${job.id} for copy ${job.barcode}?`,
          extra: h("div", { class: "approve-budget" }, lines),
          onConfirm: () => ctx.act(() => post(`/repair-jobs/${job.id}/approve`), `Job ${job.id} approved.`, reloadAll),
        });
      })();
    }

    function askCancel(job) {
      ctx.ask({
        text: `Cancel job ${job.id} for copy ${job.barcode}?`,
        onConfirm: () => ctx.act(() => post(`/repair-jobs/${job.id}/cancel`), `Job ${job.id} cancelled.`, reloadAll),
      });
    }

    function askLost(job) {
      ctx.ask({
        text: `Report job ${job.id} as lost at the provider? The copy ${job.barcode} becomes lost.`,
        onConfirm: () =>
          ctx.act(
            () => post(`/repair-jobs/${job.id}/lost`),
            (r) => (r.claim_amount ? `Job ${r.id} lost. Claim against the supplier: ${fmtAmount(r.claim_amount)}.` : `Job ${r.id} lost.`),
            reloadAll,
          ),
      });
    }

    function openEditor(job) {
      const kind = field({ name: "kind", label: "Kind", options: choices(KINDS), value: job.kind });
      const provider = field({ name: "provider", label: "Provider", options: choices(PROVIDERS), value: job.provider });
      const supplier = field({ name: "supplier_id", label: "Supplier", options: supplierOptions(false, job.supplier_id), value: job.supplier_id ?? "" });
      const priority = field({ name: "priority", label: "Priority", options: choices(PRIORITIES), value: job.priority });
      const cost = field({ name: "estimated_cost", label: "Estimated cost", inputmode: "decimal", value: job.estimated_cost });
      const note = field({ name: "note", label: "Note", type: "textarea", value: job.note });
      const node = form({
        fields: [kind, provider, supplier, priority, cost, note],
        submit: "Save",
        label: "Change job",
        extra: button("Close", () => replace(editor)),
        async onSubmit(v) {
          node.fieldErrors({});
          await ctx.act(
            () =>
              patch(`/repair-jobs/${job.id}`, {
                kind: v.kind,
                provider: v.provider,
                supplier_id: int(v.supplier_id),
                priority: v.priority,
                estimated_cost: v.estimated_cost.trim(),
                note: v.note,
              }),
            `Job ${job.id} changed.`,
            reloadAll,
            (error) => node.fieldErrors(problemsOf(error)),
          );
        },
      });
      replace(editor, section(`Change job ${job.id} (${job.barcode})`, node));
      kind.input.focus();
    }

    function openReturn(job) {
      const outcome = field({ name: "outcome", label: "Outcome", options: choices(OUTCOMES) });
      const actual = field({ name: "actual_cost", label: "Actual cost", inputmode: "decimal", value: job.estimated_cost, hint: "0.00–100000.00 TL" });
      const costNote = field({ name: "cost_note", label: "Cost note", type: "textarea", hint: "At most 500 characters." });
      const overrun = h("p", { class: "overrun-warning", role: "note", hidden: true }, "");
      const check = () => {
        const cents = toCents(actual.input.value);
        const over = cents !== null && cents * 10 > (toCents(job.estimated_cost) ?? 0) * 12;
        overrun.hidden = !over;
        overrun.textContent = over ? `The actual cost is more than 120 % of the estimate (${fmtAmount(job.estimated_cost)}): a cost note is required.` : "";
      };
      actual.input.addEventListener("input", check);
      const node = form({
        fields: [outcome, actual, costNote],
        submit: "Return",
        label: "Return job",
        extra: button("Close", () => replace(editor)),
        async onSubmit(v) {
          node.fieldErrors({});
          await ctx.act(
            () => post(`/repair-jobs/${job.id}/return`, { outcome: v.outcome, actual_cost: v.actual_cost.trim(), cost_note: v.cost_note }),
            (r) =>
              `Job ${r.id} returned (${words(r.outcome)}); actual cost ${fmtAmount(r.actual_cost)}.${r.cost_overrun ? " Cost overrun recorded." : ""}`,
            reloadAll,
            (error) => node.fieldErrors(problemsOf(error)),
          );
        },
      });
      replace(editor, section(`Return job ${job.id} (${job.barcode})`, node, overrun));
      outcome.input.focus();
      check();
    }

    function actions(job) {
      const list = [];
      if (job.status === "requested") {
        list.push(button("Approve", () => askApprove(job)), button("Change", () => openEditor(job)));
      }
      if (job.status === "approved" && job.provider === "in_house") {
        list.push(
          button("Send", () => ctx.act(() => post(`/repair-jobs/${job.id}/send`), (r) => `Job ${r.id} sent. Due back ${fmtDate(r.due_back)}.`, reloadAll)),
        );
      }
      if (job.status === "approved" && job.provider === "supplier") {
        list.push(link("Send in a shipment", "#/pre-04"));
      }
      if (job.status === "requested" || job.status === "approved") list.push(button("Cancel", () => askCancel(job)));
      if (job.status === "sent") list.push(button("Return", () => openReturn(job)), button("Report lost", () => askLost(job)));
      return h("div", { class: "row-actions" }, list);
    }

    // ---- list
    const fStatus = field({ name: "status", label: "Status", options: choices(JOB_STATUSES, { any: "Any" }) });
    const fBranch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const fProvider = field({ name: "provider", label: "Provider", options: choices(PROVIDERS, { any: "Any" }) });
    const fSupplier = field({ name: "supplier_id", label: "Supplier", options: supplierOptions(true) });
    const fKind = field({ name: "kind", label: "Kind", options: choices(KINDS, { any: "Any" }) });
    const fOverdue = field({
      name: "overdue",
      label: "Overdue",
      options: [
        { value: "", label: "Any" },
        { value: "true", label: "Yes" },
        { value: "false", label: "No" },
      ],
    });
    const fBarcode = field({ name: "barcode", label: "Barcode" });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      rowClass: (j) => (j.is_overdue ? "overdue" : undefined),
      columns: [
        { label: "ID", value: (j) => String(j.id) },
        { label: "Barcode", value: (j) => link(j.barcode, `#/pre-02/${j.copy_id}`) },
        { label: "Title", value: (j) => j.book_title },
        { label: "Branch", value: (j) => branchName(map, j.branch_id) },
        { label: "Kind", value: (j) => words(j.kind) },
        { label: "Provider", value: (j) => (j.provider === "supplier" ? `supplier: ${supplierName(suppliers, j.supplier_id)}` : "in house") },
        { label: "Priority", value: (j) => j.priority },
        { label: "Estimated cost", value: (j) => fmtAmount(j.estimated_cost) },
        { label: "Actual cost", value: (j) => fmtAmount(j.actual_cost) },
        { label: "Cost overrun", value: (j) => fmtBool(j.cost_overrun) },
        { label: "Status", value: (j) => j.status },
        { label: "Outcome", value: (j) => (j.outcome ? words(j.outcome) : dash) },
        { label: "Due back", value: (j) => fmtDate(j.due_back) },
        { label: "Overdue", value: (j) => (j.is_overdue ? h("strong", {}, "Overdue") : "No") },
        { label: "Damage loan", value: (j) => fmtText(j.loan_id) },
        { label: "Shipment", value: (j) => fmtText(j.shipment_id) },
        { label: "Actions", value: actions },
      ],
      load: (page) =>
        get("/repair-jobs", {
          page,
          page_size: 20,
          status: fStatus.input.value,
          branch_id: fBranch.input.value,
          provider: fProvider.input.value,
          supplier_id: fSupplier.input.value,
          kind: fKind.input.value,
          overdue: fOverdue.input.value,
          copy_id: copyFilter,
        }),
    });
    const filters = form({
      fields: [fStatus, fBranch, fProvider, fSupplier, fKind, fOverdue, fBarcode],
      submit: "Filter",
      label: "Filter jobs",
      cls: "filters",
      async onSubmit(v) {
        ctx.clearMessages();
        copyFilter = "";
        if (v.barcode.trim()) {
          try {
            copyFilter = (await copyByBarcode(v.barcode)).id;
          } catch (error) {
            ctx.fail(error);
            return;
          }
        }
        await list.goTo(1);
      },
    });

    replace(
      ctx.body,
      processBar,
      section("Suggestions", suggestForm, suggestionsBox),
      section("Create job", create),
      editor,
      section("Repair jobs", filters, list.el),
    );
    await Promise.all([list.goTo(1), loadSuggestions()]);
  },
};

// ---- LIB-UI-PRE-04 --------------------------------------------------------------

const shipmentsScreen = {
  id: "pre-04",
  title: "Shipments",
  module: "Preservation",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const map = await branchMap(ctx);
    const branches = await ctx.branches();
    const suppliers = await fetchAll("/suppliers");
    const picked = new Set();
    const candidates = h("div", { class: "shipment-candidates" });
    let chosen = null; // {supplier_id, branch_id} of the shown candidates

    const reloadAll = async () => {
      await Promise.all([showCandidates(), shipments.reload()]);
    };

    async function showCandidates() {
      if (!chosen) return;
      let jobs;
      try {
        jobs = await fetchAll("/repair-jobs", { status: "approved", provider: "supplier", supplier_id: chosen.supplier_id, branch_id: chosen.branch_id });
      } catch (error) {
        replace(candidates);
        ctx.fail(error);
        return;
      }
      jobs = jobs.filter((j) => j.shipment_id === null);
      for (const id of [...picked]) if (!jobs.some((j) => j.id === id)) picked.delete(id);
      const send = button("Send shipment", async () => {
        if (!picked.size) {
          ctx.fail(clientError("VALIDATION_ERROR", "Select at least one job.", { fields: [{ field: "job_ids", problem: "select at least one job" }] }));
          return;
        }
        await ctx.act(
          () => post("/repair-shipments", { supplier_id: chosen.supplier_id, job_ids: [...picked].sort((a, b) => a - b) }),
          (r) => `Shipment ${r.code} sent with ${r.job_ids.length} job${r.job_ids.length === 1 ? "" : "s"}.`,
          async () => {
            picked.clear();
            await reloadAll();
          },
        );
      });
      replace(
        candidates,
        table({
          caption: "Approved supplier jobs",
          columns: [
            {
              label: "Select",
              value: (j) => {
                const box = h("input", { type: "checkbox", name: "job_ids", value: String(j.id), id: `job-pick-${j.id}` });
                box.checked = picked.has(j.id);
                box.addEventListener("change", () => (box.checked ? picked.add(j.id) : picked.delete(j.id)));
                return h("label", { class: "pick", for: box.id }, box, ` Job ${j.id}`);
              },
            },
            { label: "Barcode", value: (j) => j.barcode },
            { label: "Title", value: (j) => j.book_title },
            { label: "Kind", value: (j) => words(j.kind) },
            { label: "Priority", value: (j) => j.priority },
            { label: "Estimated cost", value: (j) => fmtAmount(j.estimated_cost) },
            { label: "Approved at", value: (j) => fmtDate(j.approved_at) },
          ],
          rows: jobs,
        }),
        h("div", { class: "actions" }, send),
      );
    }

    const pSupplier = field({ name: "supplier_id", label: "Supplier", options: recordOptions(suppliers.filter((s) => s.is_active), (s) => s.name) });
    const pBranch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { activeOnly: true }) });
    const pick = form({
      fields: [pSupplier, pBranch],
      submit: "Show jobs",
      label: "Choose supplier and branch",
      cls: "filters",
      async onSubmit(v) {
        ctx.clearMessages();
        picked.clear();
        chosen = { supplier_id: int(v.supplier_id), branch_id: int(v.branch_id) };
        if (typeof chosen.supplier_id !== "number") {
          chosen = null;
          replace(candidates);
          ctx.fail(clientError("VALIDATION_ERROR", "Choose a supplier.", { fields: [{ field: "supplier_id", problem: "field required" }] }));
          return;
        }
        await showCandidates();
      },
    });

    const fSupplier = field({ name: "supplier_id", label: "Supplier", options: recordOptions(suppliers, (s) => s.name, { any: "Any" }) });
    const fBranch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const shipments = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Code", value: (s) => s.code },
        { label: "Supplier", value: (s) => supplierName(suppliers, s.supplier_id) },
        { label: "Branch", value: (s) => branchName(map, s.branch_id) },
        { label: "Sent at", value: (s) => fmtDateTime(s.sent_at) },
        { label: "Jobs", value: (s) => s.job_ids.join(", ") },
        { label: "Open jobs", value: (s) => String(s.open_jobs) },
      ],
      load: (page) => get("/repair-shipments", { page, page_size: 20, supplier_id: fSupplier.input.value, branch_id: fBranch.input.value }),
    });
    const filters = form({
      fields: [fSupplier, fBranch],
      submit: "Filter",
      label: "Filter shipments",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return shipments.goTo(1);
      },
    });

    replace(ctx.body, section("New shipment", pick, candidates), section("Shipments", filters, shipments.el));
    await shipments.goTo(1);
  },
};

// ---- LIB-UI-PRE-05 --------------------------------------------------------------

const reportsScreen = {
  id: "pre-05",
  title: "Preservation reports",
  module: "Preservation",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const map = await branchMap(ctx);

    // preservation report (LIB-PRE-37)
    const year = yearField(ctx);
    const yearly = pagedTable({
      onError: (e) => {
        replace(yearly.el);
        ctx.fail(e);
      },
      columns: [
        { label: "Branch", value: (r) => branchName(map, r.branch_id) },
        { label: "Budget", value: (r) => (r.budget === null ? "No budget" : fmtAmount(r.budget)) },
        { label: "Committed", value: (r) => fmtAmount(r.committed) },
        { label: "Spent", value: (r) => fmtAmount(r.spent) },
        { label: "Jobs returned", value: (r) => String(r.jobs_returned) },
        { label: "Repaired", value: (r) => String(r.repaired) },
        { label: "Unrepairable", value: (r) => String(r.unrepairable) },
        { label: "Lost", value: (r) => String(r.lost) },
        { label: "Average days", value: (r) => fmtText(r.average_days) },
        { label: "Overdue now", value: (r) => String(r.overdue_now) },
      ],
      load: (page) => get("/reports/preservation", { page, page_size: 50, year: year.input.value.trim() }),
    });
    const yearlyForm = form({
      fields: [year],
      submit: "Show",
      label: "Preservation report",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return yearly.goTo(1);
      },
    });

    // damage recovery report (LIB-PRE-38)
    const from = field({ name: "from", label: "From", type: "date", value: `${ctx.today.slice(0, 4)}-01-01` });
    const to = field({ name: "to", label: "To", type: "date", value: ctx.today });
    const recovery = pagedTable({
      onError: (e) => {
        replace(recovery.el);
        ctx.fail(e);
      },
      extraAbove: (data) =>
        definitionList([
          ["Damage fees", fmtAmount(data.totals.damage_fees)],
          ["Costs", fmtAmount(data.totals.costs)],
          ["Difference", fmtAmount(data.totals.difference)],
        ]),
      columns: [
        { label: "Job", value: (r) => String(r.job_id) },
        { label: "Copy", value: (r) => String(r.copy_id) },
        { label: "Loan", value: (r) => String(r.loan_id) },
        { label: "Member", value: (r) => link(`#${r.member_id}`, `#/mem-03/${r.member_id}`) },
        { label: "Damage fee", value: (r) => fmtAmount(r.damage_fee) },
        { label: "Actual cost", value: (r) => fmtAmount(r.actual_cost) },
        { label: "Difference", value: (r) => fmtAmount(r.difference) },
      ],
      load: (page) => get("/reports/damage-recovery", { page, page_size: 50, from: from.input.value, to: to.input.value }),
    });
    const recoveryForm = form({
      fields: [from, to],
      submit: "Show",
      label: "Damage recovery report",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return recovery.goTo(1);
      },
    });

    replace(
      ctx.body,
      section("Preservation report", yearlyForm, yearly.el),
      section("Damage recovery report", recoveryForm, recovery.el),
    );
    await Promise.all([yearly.goTo(1), recovery.goTo(1)]);
  },
};

// ---- LIB-UI-PRE-06 --------------------------------------------------------------

const repairsOnBookPageScreen = {
  id: "pre-06",
  title: "Repairs on the book page",
  module: "Preservation",
  roles: ["all"],
  part: true,
  async render(ctx) {
    replace(ctx.body, h("p", {}, "Repairs are shown in the availability of the book page."), link("Book page", "#/cat-02"));
  },
};

/** The availability rows of a book carry `expected_back` (LIB-PRE-33): the latest `due_back` of its `sent` jobs at that branch. */
async function repairsPart(ctx, book) {
  const map = await branchMap(ctx);
  const rows = (book.availability || []).filter((a) => a.expected_back);
  return section(
    "In repair",
    table({
      columns: [
        { label: "Branch", value: (a) => branchName(map, a.branch_id) },
        { label: "Repair", value: (a) => `in repair, expected back on ${fmtDate(a.expected_back)}` },
      ],
      rows,
    }),
  );
}

bookPageParts.push({ id: "pre-06", render: repairsPart });

export const preservationScreens = [budgetsScreen, inspectionScreen, jobsScreen, shipmentsScreen, reportsScreen, repairsOnBookPageScreen];
