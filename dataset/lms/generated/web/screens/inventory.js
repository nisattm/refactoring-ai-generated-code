// Module 24: inventory counts (counts, scanning, closing, problems, found copies, report).

import { clientError, fetchAll, get, post, del } from "../api.js";
import {
  branchOptions,
  button,
  definitionList,
  field,
  fieldProblems,
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

const COUNT_STATUSES = ["open", "closed", "applied", "cancelled"];
const MAX_MISSING_FOR_LIBRARIAN = 10;

// Scan results (LIB-INV-08): label, short meaning. The colour is in inventory.css (class inv-<result>).
const RESULTS = {
  expected: ["Expected", "On the list and now counted."],
  duplicate: ["Duplicate", "This copy was already scanned in this count."],
  unknown: ["Unknown", "No copy has this barcode."],
  found_lost: ["Found lost", "The copy is recorded as lost or missing."],
  withdrawn: ["Withdrawn", "The copy was withdrawn."],
  wrong_branch: ["Wrong branch", "The copy belongs to another branch."],
  unexpected_status: ["Unexpected status", "The copy has a status that does not belong on a shelf."],
  out_of_scope: ["Out of scope", "The copy is not in the shelves of this count."],
};

const resultLabel = (result) => RESULTS[result]?.[0] ?? words(result);
const resultChip = (result) => h("span", { class: `inv-result inv-${result}` }, resultLabel(result));

// ---- helpers ---------------------------------------------------------------------

const countId = (ctx) => (/^\d+$/.test(ctx.param) ? Number(ctx.param) : null);
const loadCount = (id) => get(`/inventory-counts/${id}`);
const percent = (part, whole) => (whole > 0 ? Math.round((part / whole) * 100) : 100);
const accuracyText = (summary) => (summary ? `${summary.accuracy}%` : "–");

function countLabel(count, map) {
  return `#${count.id} ${count.name} (${branchName(map, count.branch_id)}, ${count.status})`;
}

function scopeText(count) {
  return count.shelf_prefix ? `Shelves starting with ${count.shelf_prefix}` : "Whole branch";
}

function countNav(id) {
  return h(
    "nav",
    { class: "inv-nav", "aria-label": "Count screens" },
    link("Counts", "#/inv-01"),
    link("Scanning", `#/inv-02/${id}`),
    link("Closing", `#/inv-03/${id}`),
    link("Problems", `#/inv-04/${id}`),
  );
}

function progressBar(progress) {
  const done = progress.scanned_expected;
  const total = progress.expected;
  const pct = percent(done, total);
  return h(
    "div",
    { class: "inv-progress" },
    h("progress", { max: Math.max(total, 1), value: done, "aria-label": "Expected copies scanned" }, `${pct}%`),
    h("span", { class: "inv-progress-text" }, `${done} of ${total} expected copies scanned (${pct}%), ${progress.remaining} remaining`),
  );
}

function problemsTable(progress) {
  const order = ["unknown", "duplicate", "found_lost", "withdrawn", "wrong_branch", "unexpected_status", "out_of_scope"];
  return table({
    columns: [
      { label: "Result", value: (r) => resultChip(r) },
      { label: "Scans", value: (r) => String(progress.problems[r] ?? 0) },
    ],
    rows: order,
  });
}

/** Without a count in the route: a field to choose one. */
async function chooseCount(ctx, screenId, statuses) {
  const map = await branchMap(ctx);
  const lists = await Promise.all(statuses.map((s) => fetchAll("/inventory-counts", s ? { status: s } : {})));
  const counts = lists.flat().sort((a, b) => b.id - a.id);
  const choose = field({
    name: "count_id",
    label: "Count",
    options: counts.length ? recordOptions(counts, (c) => countLabel(c, map)) : [{ value: "", label: "No counts" }],
  });
  replace(
    ctx.body,
    form({
      fields: [choose],
      submit: "Open",
      label: "Choose a count",
      onSubmit(v) {
        if (v.count_id) ctx.navigate(`#/${screenId}/${v.count_id}`);
      },
    }),
  );
}

function countFacts(count, map) {
  return definitionList([
    ["Count", `#${count.id} ${count.name}`],
    ["Branch", branchName(map, count.branch_id)],
    ["Scope", scopeText(count)],
    ["Status", count.status + (count.cancel_reason ? ` (${words(count.cancel_reason)})` : "")],
    ["Started", fmtDateTime(count.started_at)],
    ["Closed", fmtDateTime(count.closed_at)],
    ["Applied", fmtDateTime(count.applied_at)],
    ["Expected copies", String(count.expected_count)],
  ]);
}

async function copyTitle(ctx, copyId) {
  if (copyId === null || copyId === undefined) return "–";
  try {
    const copy = await ctx.copy(copyId);
    return (await ctx.book(copy.book_id)).title;
  } catch {
    return `copy #${copyId}`;
  }
}

// ---- LIB-UI-INV-01 ---------------------------------------------------------------

const countsScreen = {
  id: "inv-01",
  title: "Counts",
  module: "Inventory counts",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const map = await branchMap(ctx);

    // start form
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { activeOnly: true }), required: true });
    const name = field({ name: "name", label: "Name", required: true, hint: "1–200 characters.", attrs: { maxlength: "200" } });
    const prefix = field({
      name: "shelf_prefix",
      label: "Shelf prefix",
      hint: "Optional, 1–20 characters. Leave empty to count the whole branch.",
      attrs: { maxlength: "20" },
    });
    const linkBox = h("div", { class: "inv-link" });
    const start = form({
      fields: [branch, name, prefix],
      submit: "Start",
      label: "Start a count",
      cls: "inv-start",
      async onSubmit(v) {
        replace(linkBox);
        start.fieldErrors({});
        await ctx.act(
          () =>
            post(
              "/inventory-counts",
              omitNull({ branch_id: int(v.branch_id), name: v.name.trim(), shelf_prefix: text(v.shelf_prefix) }),
            ),
          (c) => `Count "${c.name}" started with ${c.expected_count} expected copies.`,
          (c) => {
            replace(linkBox, link("Open scanning", `#/inv-02/${c.id}`));
            return list.goTo(1);
          },
          (error) => {
            start.fieldErrors(fieldProblems(error));
            if (error.code === "COUNT_SCOPE_OVERLAP" && error.details?.count_id) {
              replace(linkBox, link("Open the overlapping count", `#/inv-02/${error.details.count_id}`));
            }
          },
        );
      },
    });

    // list
    const filterBranch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const filterStatus = field({
      name: "status",
      label: "Status",
      options: [{ value: "", label: "Any" }, ...COUNT_STATUSES.map((s) => ({ value: s, label: s }))],
    });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "ID", value: (c) => String(c.id) },
        { label: "Name", value: (c) => c.name },
        { label: "Branch", value: (c) => branchName(map, c.branch_id) },
        { label: "Scope", value: (c) => c.shelf_prefix ?? "Whole branch" },
        { label: "Status", value: (c) => c.status + (c.cancel_reason ? ` (${words(c.cancel_reason)})` : "") },
        { label: "Started", value: (c) => fmtDate(c.started_at) },
        {
          label: "Progress",
          value: (c) =>
            h(
              "div",
              { class: "inv-progress" },
              h("progress", { max: Math.max(c.progress.expected, 1), value: c.progress.scanned_expected, "aria-label": `Progress of count ${c.id}` }),
              h("span", { class: "inv-progress-text" }, `${c.progress.scanned_expected} of ${c.progress.expected} scanned`),
            ),
        },
        { label: "Accuracy", value: (c) => accuracyText(c.summary) },
        {
          label: "Actions",
          value: (c) =>
            h(
              "span",
              { class: "row-actions" },
              c.status === "open" ? link("Scan", `#/inv-02/${c.id}`) : null,
              link(c.status === "open" || c.status === "closed" ? "Close or apply" : "Summary", `#/inv-03/${c.id}`),
              link("Problems", `#/inv-04/${c.id}`),
            ),
        },
      ],
      async load(page) {
        const data = await get("/inventory-counts", {
          page,
          page_size: 20,
          branch_id: filterBranch.input.value,
          status: filterStatus.input.value,
        });
        data.items = await Promise.all(
          data.items.map(async (c) => {
            const detail = await loadCount(c.id);
            return { ...c, progress: detail.progress, summary: detail.summary };
          }),
        );
        return data;
      },
    });
    const filters = form({
      fields: [filterBranch, filterStatus],
      submit: "Filter",
      label: "Count filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return list.goTo(1);
      },
    });
    const process = button("Process", () =>
      ctx.act(
        () => post("/inventory/process"),
        (r) => `Processed. Expired counts: ${r.expired_counts}. Copies marked lost: ${r.marked_lost}.`,
        () => list.reload(),
      ),
    );

    replace(
      ctx.body,
      section("Start a count", start, linkBox),
      section("Counts", filters, list.el, h("div", { class: "actions" }, process)),
    );
    await list.goTo(1);
  },
};

// ---- LIB-UI-INV-02 ---------------------------------------------------------------

/** The newest `n` scans (oldest first) and the total: the list is ordered by id. */
async function recentScans(id, n) {
  const path = `/inventory-counts/${id}/scans`;
  const first = await get(path, { page: 1, page_size: 1 });
  if (!first.total) return { total: 0, items: [] };
  const pages = Math.ceil(first.total / n);
  let items = (await get(path, { page: pages, page_size: n })).items;
  if (items.length < n && pages > 1) items = [...(await get(path, { page: pages - 1, page_size: n })).items, ...items];
  return { total: first.total, items: items.slice(-n) };
}

const scanningScreen = {
  id: "inv-02",
  title: "Scanning",
  module: "Inventory counts",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const id = countId(ctx);
    if (id === null) return chooseCount(ctx, "inv-02", ["open"]);

    const map = await branchMap(ctx);
    let count = await loadCount(id);
    let last = null;
    const factsBox = h("div", { class: "inv-facts" });
    const progressBox = h("div", { class: "inv-progress-box" });
    const resultBox = h("div", { class: "inv-last", "aria-live": "polite" });
    const recentBox = h("div", { class: "inv-recent" });
    const formBox = h("div", { class: "inv-scan-box" });
    const scanField = field({
      name: "barcode",
      label: "Barcode",
      hint: "Scan or type a barcode and press Enter.",
      attrs: { autocomplete: "off", autocapitalize: "characters", spellcheck: "false" },
    });
    const undo = button("Undo last scan", () => undoLast());

    async function refresh() {
      count = await loadCount(id);
      replace(factsBox, countFacts(count, map));
      replace(progressBox, progressBar(count.progress), problemsTable(count.progress));
      const open = count.status === "open";
      formBox.hidden = !open;
      const recent = await recentScans(id, 10);
      last = recent.items[recent.items.length - 1] || null;
      undo.disabled = !open || !last;
      const rows = recent.items.slice().reverse();
      await Promise.all(rows.map(async (s) => (s._title = await copyTitle(ctx, s.copy_id))));
      replace(
        recentBox,
        h("h3", {}, "Latest scans"),
        table({
          columns: [
            { label: "Scan", value: (s) => String(s.id) },
            { label: "Barcode", value: (s) => s.barcode },
            { label: "Title", value: (s) => s._title },
            { label: "Result", value: (s) => resultChip(s.result) },
            { label: "Scanned at", value: (s) => fmtDateTime(s.scanned_at) },
          ],
          rows,
          rowClass: (s) => `inv-row inv-row-${s.result}`,
        }),
        h("p", { class: "hint" }, `${recent.total} scans in this count.`),
      );
      if (!open) {
        replace(resultBox, h("p", {}, `This count is ${count.status}; scans can no longer be added.`, " ", link("Go to closing", `#/inv-03/${id}`)));
      }
    }

    async function showResults(scans) {
      const rows = await Promise.all(
        scans.map(async (s) => {
          const title = await copyTitle(ctx, s.copy_id);
          return h(
            "li",
            { class: `inv-scan-result inv-box-${s.result}` },
            resultChip(s.result),
            " ",
            h("strong", {}, s.barcode),
            title !== "–" ? ` – ${title}` : "",
            h("span", { class: "inv-meaning" }, ` ${RESULTS[s.result]?.[1] ?? ""}`),
          );
        }),
      );
      replace(resultBox, h("ul", { class: "inv-scan-results" }, rows.slice(-5)), scans.length > 5 ? h("p", { class: "hint" }, `${scans.length} scans were added; the last 5 are shown.`) : null);
    }

    async function undoLast() {
      if (!last) return;
      const scan = last;
      await ctx.act(
        () => del(`/inventory-scans/${scan.id}`),
        `Last scan undone: ${scan.barcode} (${resultLabel(scan.result)}).`,
        async () => {
          replace(resultBox);
          await refresh();
        },
      );
      scanField.input.focus();
    }

    const scanForm = form({
      fields: [scanField],
      submit: "Scan",
      label: "Scan barcodes",
      cls: "inv-scan",
      async onSubmit(v) {
        const barcodes = v.barcode.split(/[\s,;]+/).filter(Boolean);
        if (!barcodes.length) {
          ctx.fail(clientError("VALIDATION_ERROR", "Enter a barcode.", { fields: [{ field: "barcode", problem: "field required" }] }));
          scanField.input.focus();
          return;
        }
        await ctx.act(
          () => post(`/inventory-counts/${id}/scans`, { barcodes }),
          (r) => (r.scans.length === 1 ? `Scanned ${r.scans[0].barcode}: ${resultLabel(r.scans[0].result)}.` : `${r.scans.length} barcodes scanned.`),
          async (r) => {
            scanField.input.value = "";
            await showResults(r.scans);
            await refresh();
          },
        );
        scanField.input.focus();
      },
    });
    formBox.append(scanForm, h("div", { class: "actions" }, undo));

    replace(
      ctx.body,
      countNav(id),
      section("Count", factsBox),
      section("Scan", formBox, resultBox),
      section("Progress", progressBox),
      section("Scans", recentBox),
    );
    await refresh();
    if (count.status === "open") scanField.input.focus();
  },
};

// ---- LIB-UI-INV-03 ---------------------------------------------------------------

function linesTable(ctx, id, outcome, title) {
  const list = pagedTable({
    onError: (e) => ctx.fail(e),
    columns: [
      { label: "Barcode", value: (l) => l.barcode },
      { label: "Title", value: (l) => l.book_title },
      { label: "Shelf location", value: (l) => fmtText(l.shelf_location) },
      { label: "Outcome", value: (l) => l.outcome },
    ],
    load: (page) => get(`/inventory-counts/${id}/lines`, { page, page_size: 20, outcome }),
  });
  return { node: section(title, list.el), start: () => list.goTo(1) };
}

const closingScreen = {
  id: "inv-03",
  title: "Closing",
  module: "Inventory counts",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const id = countId(ctx);
    if (id === null) return chooseCount(ctx, "inv-03", [""]);
    const map = await branchMap(ctx);

    async function show() {
      const count = await loadCount(id);
      const sections = [countNav(id), section("Count", countFacts(count, map))];
      const starts = [];

      if (count.status === "open") {
        sections.push(section("Progress", progressBar(count.progress), problemsTable(count.progress)));
      }
      if (count.summary) {
        const s = count.summary;
        sections.push(
          section(
            "Summary",
            definitionList([
              ["Accuracy", `${s.accuracy}%`],
              ["Expected", String(s.expected)],
              ["Found", String(s.found)],
              ["Missing", String(s.missing)],
              ["Moved", String(s.moved)],
            ]),
          ),
        );
      }
      if (count.status === "closed" || count.status === "applied") {
        const missing = linesTable(ctx, id, "missing", "Missing copies");
        const moved = linesTable(ctx, id, "moved", "Moved copies");
        sections.push(missing.node, moved.node);
        starts.push(missing.start, moved.start);
      }

      const actions = h("div", { class: "actions" });
      if (count.status === "open") {
        actions.append(
          button("Close", () =>
            ctx.act(
              () => post(`/inventory-counts/${id}/close`),
              (c) => `Count closed. Accuracy ${c.summary.accuracy}%: ${c.summary.found} found, ${c.summary.missing} missing, ${c.summary.moved} moved.`,
              show,
            ),
          ),
        );
      }
      if (count.status === "closed") {
        const tooMany = count.summary && count.summary.missing > MAX_MISSING_FOR_LIBRARIAN;
        if (tooMany && !ctx.isAdmin) {
          sections.push(
            h(
              "p",
              { class: "inv-note", role: "note" },
              `${count.summary.missing} copies are missing, more than ${MAX_MISSING_FOR_LIBRARIAN}: only an admin can apply this count.`,
            ),
          );
        } else {
          actions.append(
            button("Apply", () =>
              ctx.act(
                () => post(`/inventory-counts/${id}/apply`),
                (r) => `Count applied. Marked missing: ${r.missing_marked}. Found again: ${r.found}. Relocated: ${r.relocated}.`,
                show,
              ),
            ),
          );
        }
      }
      if (count.status === "open" || count.status === "closed") {
        actions.append(
          button("Cancel", () =>
            ctx.ask({
              text: `Cancel the count "${count.name}"? The copies do not change.`,
              onConfirm: () =>
                ctx.act(() => post(`/inventory-counts/${id}/cancel`), "Count cancelled.", show),
            }),
          ),
        );
      }
      if (count.status === "closed") {
        actions.prepend(h("p", { class: "hint" }, "Applying marks the missing copies as missing, returns found copies to circulation and corrects their branch."));
      }
      if (actions.children.length) sections.push(actions);
      replace(ctx.body, sections);
      await Promise.all(starts.map((s) => s()));
    }
    await show();
  },
};

// ---- LIB-UI-INV-04 ---------------------------------------------------------------

const PROBLEM_GROUPS = [
  ["unknown", "Unknown barcodes", "No copy has this barcode. Applying changes nothing for these scans."],
  [
    "wrong_branch",
    "Wrong branch",
    "The copy belongs to another branch. Applying moves a copy that is available to the branch of this count and releases it; other copies stay as they are.",
  ],
  [
    "unexpected_status",
    "Unexpected status",
    "The copy has a status that does not belong on a shelf (for example lent). Applying changes nothing for these scans.",
  ],
  [
    "found_lost",
    "Found lost",
    "The copy is recorded as lost or missing. Applying brings it back into circulation at the branch of this count.",
  ],
];

function effectText(group, scan, count, map) {
  const copy = scan._copy;
  const target = branchName(map, count.branch_id);
  if (group === "unknown") return "No change.";
  if (group === "unexpected_status") return "No change.";
  if (!copy) return "No change.";
  if (group === "found_lost") {
    return copy.status === "lost" || copy.status === "missing"
      ? `Moves to ${target}, missing date cleared, released.`
      : `Skipped: the copy is now ${words(copy.status)}.`;
  }
  if (group === "wrong_branch") {
    if (copy.status !== "available") return `Skipped: the copy is ${words(copy.status)}, not available.`;
    return copy.current_branch_id === count.branch_id ? "No change." : `Moves to ${target}, released.`;
  }
  return "No change.";
}

const problemsScreen = {
  id: "inv-04",
  title: "Problems",
  module: "Inventory counts",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const id = countId(ctx);
    if (id === null) return chooseCount(ctx, "inv-04", [""]);
    const map = await branchMap(ctx);
    let count = null;

    function groupSection(result, title, meaning, pending) {
      const showEffect = count.status === "open" || count.status === "closed";
      const list = pagedTable({
        onError: (e) => ctx.fail(e),
        columns: [
          { label: "Scan", value: (s) => String(s.id) },
          { label: "Barcode", value: (s) => s.barcode },
          { label: "Title", value: (s) => s._title },
          { label: "Copy status", value: (s) => (s._copy ? words(s._copy.status) : "–") },
          { label: "Current branch", value: (s) => (s._copy ? branchName(map, s._copy.current_branch_id) : "–") },
          { label: "Shelf", value: (s) => fmtText(s._copy?.shelf_location) },
          { label: "Scanned at", value: (s) => fmtDateTime(s.scanned_at) },
          ...(showEffect ? [{ label: "What applying will do", value: (s) => effectText(result, s, count, map) }] : []),
          ...(count.status === "open"
            ? [
                {
                  label: "Actions",
                  value: (s) =>
                    button("Undo", () => ctx.act(() => del(`/inventory-scans/${s.id}`), `Scan of ${s.barcode} removed.`, show)),
                },
              ]
            : []),
        ],
        async load(page) {
          const data = await get(`/inventory-counts/${id}/scans`, { page, page_size: 20, result });
          await Promise.all(
            data.items.map(async (s) => {
              s._title = await copyTitle(ctx, s.copy_id);
              s._copy = null;
              if (s.copy_id !== null) {
                try {
                  // a fresh read: the effect of applying depends on the current state of the copy
                  s._copy = await get(`/copies/${s.copy_id}`);
                } catch {
                  s._copy = null;
                }
              }
            }),
          );
          return data;
        },
      });
      pending.push(() => list.goTo(1));
      return section(`${title} (${count.progress.problems[result]})`, h("p", { class: "hint" }, meaning), list.el);
    }

    function summaryText() {
      if (count.status === "applied") return "This count has been applied.";
      if (count.status === "cancelled") return "This count was cancelled; nothing will change.";
      if (count.status === "closed") {
        const missing = count.summary ? count.summary.missing : 0;
        return `Applying marks ${missing} missing copies as missing, brings found lost copies back into circulation here and moves available copies of other branches to this branch.`;
      }
      return `${count.progress.remaining} expected copies are not scanned yet. When the count is closed and applied, those still on a shelf are marked as missing.`;
    }

    async function show() {
      count = await loadCount(id);
      const pending = [];
      const sections = [
        countNav(id),
        section("Count", countFacts(count, map)),
        section("What applying will do", h("p", {}, summaryText()), problemsTable(count.progress)),
        ...PROBLEM_GROUPS.map(([result, title, meaning]) => groupSection(result, title, meaning, pending)),
      ];
      replace(ctx.body, sections);
      await Promise.all(pending.map((start) => start()));
    }
    await show();
  },
};

// ---- LIB-UI-INV-05 ---------------------------------------------------------------

const foundScreen = {
  id: "inv-05",
  title: "Found copies",
  module: "Inventory counts",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const map = await branchMap(ctx);
    const barcode = field({ name: "barcode", label: "Barcode", required: true, attrs: { autocomplete: "off" } });
    const branch = field({
      name: "branch_id",
      label: "Branch",
      options: branchOptions(branches, { activeOnly: true }),
      required: true,
      hint: "The branch where the copy was found.",
    });
    const resultBox = h("div", { class: "inv-found" });
    const node = form({
      fields: [barcode, branch],
      submit: "Mark as found",
      label: "Mark a copy as found",
      async onSubmit(v) {
        replace(resultBox);
        await ctx.act(
          async () => {
            const wanted = v.barcode.trim();
            if (!wanted) {
              throw clientError("VALIDATION_ERROR", "Enter a barcode.", { fields: [{ field: "barcode", problem: "field required" }] });
            }
            const copy = await get(`/copies/by-barcode/${encodeURIComponent(wanted)}`);
            return post(`/copies/${copy.id}/found`, { branch_id: int(v.branch_id) });
          },
          (copy) => `Copy ${copy.barcode} marked as found at ${branchName(map, int(v.branch_id))}.`,
          async (copy) => {
            const title = await copyTitle(ctx, copy.id);
            barcode.input.value = "";
            replace(
              resultBox,
              section(
                "Copy",
                definitionList([
                  ["Barcode", copy.barcode],
                  ["Title", title],
                  ["Status", words(copy.status)],
                  ["Current branch", branchName(map, copy.current_branch_id)],
                  ["Shelf location", fmtText(copy.shelf_location)],
                  ["Missing since", fmtDate(copy.missing_since)],
                ]),
              ),
            );
          },
        );
      },
    });
    replace(
      ctx.body,
      section("Mark a missing or lost copy as found", h("p", { class: "hint" }, "Only copies with status missing or lost can be marked as found."), node),
      resultBox,
    );
  },
};

// ---- LIB-UI-INV-06 ---------------------------------------------------------------

const reportScreen = {
  id: "inv-06",
  title: "Inventory report",
  module: "Inventory counts",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const map = await branchMap(ctx);
    const year = field({
      name: "year",
      label: "Year",
      type: "number",
      value: ctx.today.slice(0, 4),
      min: "2000",
      max: "2100",
      step: "1",
    });
    const box = h("div", { class: "inv-report" });

    async function load() {
      const data = await get("/reports/inventory", { year: year.input.value.trim() });
      replace(
        box,
        table({
          columns: [
            { label: "Branch", value: (r) => branchName(map, r.branch_id) },
            { label: "Counts applied", value: (r) => String(r.counts_applied) },
            { label: "Last applied on", value: (r) => fmtDate(r.last_applied_on) },
            { label: "Expected", value: (r) => String(r.expected) },
            { label: "Found", value: (r) => String(r.found) },
            { label: "Missing", value: (r) => String(r.missing) },
            { label: "Accuracy", value: (r) => `${r.accuracy}%` },
            { label: "Missing now", value: (r) => String(r.missing_now) },
            { label: "Found again", value: (r) => String(r.found_again) },
          ],
          rows: data.items,
        }),
      );
    }

    const node = form({
      fields: [year],
      submit: "Show",
      label: "Inventory report",
      cls: "filters",
      async onSubmit() {
        ctx.clearMessages();
        try {
          await load();
        } catch (error) {
          ctx.fail(error);
        }
      },
    });
    replace(ctx.body, node, box);
    await load();
  },
};

export const inventoryScreens = [countsScreen, scanningScreen, closingScreen, problemsScreen, foundScreen, reportScreen];
