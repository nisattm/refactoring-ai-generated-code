// Modules 11–13: branches and transfers, purchasing, audit log, import and export.

import { api, download, fetchAll, get, patch, post } from "../api.js";
import { clientError } from "../api.js";
import { findBook } from "../context.js";
import {
  BOOLEAN_FILTER,
  branchOptions,
  button,
  choices,
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
  recordOptions,
  replace,
  section,
  table,
  text,
  words,
} from "../ui.js";
import { branchMap, branchName, bookLink, withCopies } from "../views.js";

// ---- LIB-UI-BR-01 ----------------------------------------------------------------

const ACTIVE_OPTIONS = [
  { value: "true", label: "Yes" },
  { value: "false", label: "No" },
];

const branchesScreen = {
  id: "br-01",
  title: "Branches",
  module: "Branches and transfers",
  roles: ["all"],
  async render(ctx) {
    const editor = h("div", { class: "branch-editor" });
    const active = field({ name: "is_active", label: "Active", options: BOOLEAN_FILTER });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Code", value: (b) => b.code },
        { label: "Name", value: (b) => b.name },
        { label: "Address", value: (b) => fmtText(b.address) },
        { label: "Active", value: (b) => fmtBool(b.is_active) },
        ...(ctx.isAdmin ? [{ label: "Actions", value: (b) => button("Edit", () => openEditor(b)) }] : []),
      ],
      load: (page) => get("/branches", { page, page_size: 20, is_active: active.input.value }),
    });
    const filters = form({
      fields: [active],
      submit: "Filter",
      label: "Branch filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    const reload = async () => {
      ctx.forgetBranches();
      await list.reload();
    };

    function openEditor(branch) {
      const name = field({ name: "name", label: "Name", value: branch.name });
      const address = field({ name: "address", label: "Address", value: branch.address });
      const isActive = field({ name: "is_active", label: "Active", options: ACTIVE_OPTIONS, value: String(branch.is_active) });
      const save = (v) =>
        ctx.act(
          () => patch(`/branches/${branch.id}`, { name: v.name.trim(), address: v.address.trim(), is_active: v.is_active === "true" }),
          (b) => `Branch ${b.code} saved.`,
          async () => {
            await reload();
            replace(editor);
          },
        );
      const node = form({
        fields: [name, address, isActive],
        submit: "Save",
        label: "Change branch",
        extra: button("Close", () => replace(editor)),
        onSubmit(v) {
          if (branch.is_active && v.is_active === "false") {
            ctx.ask({ text: `Deactivate branch ${branch.code}?`, onConfirm: () => save(v) });
          } else {
            save(v);
          }
        },
      });
      replace(editor, section(`Change branch ${branch.code}`, node));
    }

    let create = null;
    if (ctx.isAdmin) {
      const code = field({ name: "code", label: "Code", hint: "2–10 characters: A–Z and 0–9." });
      const name = field({ name: "name", label: "Name" });
      const address = field({ name: "address", label: "Address" });
      create = form({
        fields: [code, name, address],
        submit: "Create",
        label: "Create branch",
        async onSubmit(v) {
          create.fieldErrors({});
          const done = await ctx.act(
            () => post("/branches", { code: v.code.trim(), name: v.name.trim(), address: v.address.trim() }),
            (b) => `Branch ${b.code} created.`,
            reload,
            (error) => create.fieldErrors(fieldProblems(error)),
          );
          if (done) {
            code.input.value = "";
            name.input.value = "";
            address.input.value = "";
          }
        },
      });
    }
    replace(ctx.body, create ? section("Create branch", create) : null, filters, list.el, editor);
    await list.goTo(1);
  },
};

// ---- LIB-UI-BR-02 ----------------------------------------------------------------

const TRANSFER_STATUSES = ["in_transit", "received"];
const TRANSFER_REASONS = ["return_home", "reservation", "relocation"];

const transfersScreen = {
  id: "br-02",
  title: "Transfers",
  module: "Branches and transfers",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const map = await branchMap(ctx);

    const barcode = field({ name: "barcode", label: "Barcode" });
    const target = field({ name: "to_branch_id", label: "Target branch", options: branchOptions(branches, { activeOnly: true }) });

    const fStatus = field({ name: "status", label: "Status", options: choices(TRANSFER_STATUSES, { any: "Any" }) });
    const fReason = field({ name: "reason", label: "Reason", options: choices(TRANSFER_REASONS, { any: "Any" }) });
    const fFrom = field({ name: "from_branch_id", label: "From branch", options: branchOptions(branches, { any: "Any" }) });
    const fTo = field({ name: "to_branch_id", label: "To branch", options: branchOptions(branches, { any: "Any" }) });
    const fBarcode = field({ name: "barcode", label: "Copy barcode" });

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "ID", value: (t) => String(t.id) },
        { label: "Barcode", value: (t) => t._copy.barcode },
        { label: "Title", value: (t) => bookLink(t._book) },
        { label: "From", value: (t) => branchName(map, t.from_branch_id) },
        { label: "To", value: (t) => branchName(map, t.to_branch_id) },
        { label: "Reason", value: (t) => words(t.reason) },
        { label: "Started", value: (t) => fmtDate(t.started_on) },
        { label: "Expected", value: (t) => fmtDate(t.expected_on) },
        { label: "Status", value: (t) => words(t.status) },
        { label: "Received", value: (t) => fmtDate(t.received_on) },
      ],
      load: async (page) => {
        const query = { page, page_size: 20, status: fStatus.input.value, reason: fReason.input.value, from_branch_id: fFrom.input.value, to_branch_id: fTo.input.value };
        if (fBarcode.input.value.trim()) query.copy_id = (await get(`/copies/by-barcode/${encodeURIComponent(fBarcode.input.value.trim())}`)).id;
        const data = await get("/transfers", query);
        await withCopies(ctx, data.items);
        return data;
      },
    });

    const relocate = form({
      fields: [barcode, target],
      submit: "Relocate",
      label: "Relocate a copy",
      async onSubmit(v) {
        const done = await ctx.act(
          async () => {
            const wanted = v.barcode.trim();
            if (!wanted) throw clientError("VALIDATION_ERROR", "Enter a barcode.", { fields: [{ field: "barcode", problem: "field required" }] });
            const copy = await get(`/copies/by-barcode/${encodeURIComponent(wanted)}`);
            return post("/transfers", { copy_id: copy.id, to_branch_id: Number(v.to_branch_id) });
          },
          (t) => `Transfer started. Expected on ${fmtDate(t.expected_on)}.`,
          () => list.goTo(1),
        );
        if (done) barcode.input.value = "";
      },
    });
    const filters = form({
      fields: [fStatus, fReason, fFrom, fTo, fBarcode],
      submit: "Filter",
      label: "Transfer filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    replace(
      ctx.body,
      section("Relocate a copy", relocate),
      h("div", { class: "actions" }, button("Process arrivals", () => ctx.act(() => post("/transfers/process-arrivals"), (r) => `Transfers received: ${r.received}`, () => list.reload()))),
      section("Transfer list", filters, list.el),
    );
    await list.goTo(1);
  },
};

// ---- LIB-UI-PUR-01 ---------------------------------------------------------------

const suppliersScreen = {
  id: "pur-01",
  title: "Suppliers",
  module: "Purchasing",
  roles: ["librarian", "admin"],
  async render(ctx) {
    const editor = h("div", { class: "supplier-editor" });
    const q = field({ name: "q", label: "Search" });
    const active = field({ name: "is_active", label: "Active", options: BOOLEAN_FILTER });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "ID", value: (s) => String(s.id) },
        { label: "Name", value: (s) => s.name },
        { label: "Email", value: (s) => fmtText(s.email) },
        { label: "Phone", value: (s) => fmtText(s.phone) },
        { label: "Active", value: (s) => fmtBool(s.is_active) },
        { label: "Actions", value: (s) => button("Edit", () => openEditor(s)) },
      ],
      load: (page) => get("/suppliers", { page, page_size: 20, q: q.input.value.trim(), is_active: active.input.value }),
    });
    const filters = form({
      fields: [q, active],
      submit: "Filter",
      label: "Supplier filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    const name = field({ name: "name", label: "Name" });
    const email = field({ name: "email", label: "Email", type: "email" });
    const phone = field({ name: "phone", label: "Phone" });
    const create = form({
      fields: [name, email, phone],
      submit: "Create",
      label: "Create supplier",
      async onSubmit(v) {
        create.fieldErrors({});
        const done = await ctx.act(
          () => post("/suppliers", { name: v.name.trim(), email: text(v.email), phone: text(v.phone) }),
          (s) => `Supplier ${s.name} created.`,
          () => list.reload(),
          (error) => create.fieldErrors(fieldProblems(error)),
        );
        if (done) {
          name.input.value = "";
          email.input.value = "";
          phone.input.value = "";
        }
      },
    });
    function openEditor(supplier) {
      const fName = field({ name: "name", label: "Name", value: supplier.name });
      const fEmail = field({ name: "email", label: "Email", type: "email", value: supplier.email });
      const fPhone = field({ name: "phone", label: "Phone", value: supplier.phone });
      const fActive = field({ name: "is_active", label: "Active", options: ACTIVE_OPTIONS, value: String(supplier.is_active) });
      const node = form({
        fields: [fName, fEmail, fPhone, fActive],
        submit: "Save",
        label: "Change supplier",
        extra: button("Close", () => replace(editor)),
        onSubmit(v) {
          node.fieldErrors({});
          const save = () =>
            ctx.act(
              () => patch(`/suppliers/${supplier.id}`, { name: v.name.trim(), email: text(v.email), phone: text(v.phone), is_active: v.is_active === "true" }),
              (s) => `Supplier ${s.name} saved.`,
              async () => {
                await list.reload();
                replace(editor);
              },
              (error) => node.fieldErrors(fieldProblems(error)),
            );
          if (supplier.is_active && v.is_active === "false") {
            ctx.ask({ text: `Deactivate supplier ${supplier.name}?`, onConfirm: save });
          } else {
            save();
          }
        },
      });
      replace(editor, section(`Change supplier ${supplier.name}`, node));
    }
    replace(ctx.body, section("Create supplier", create), section("Supplier list", filters, list.el), editor);
    await list.goTo(1);
  },
};

// ---- LIB-UI-PUR-02 ---------------------------------------------------------------

const ORDER_STATUSES = ["draft", "ordered", "partially_received", "received", "cancelled"];

const ordersScreen = {
  id: "pur-02",
  title: "Purchase orders",
  module: "Purchasing",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const map = await branchMap(ctx);
    const suppliers = await fetchAll("/suppliers");
    const supplierName = (id) => suppliers.find((s) => s.id === id)?.name || `#${id}`;
    const editor = h("div", { class: "order-editor" });
    const receivePanel = h("div", { class: "receive-panel" });
    let receiving = null;

    const fStatus = field({ name: "status", label: "Status", options: choices(ORDER_STATUSES, { any: "Any" }) });
    const fSupplier = field({ name: "supplier_id", label: "Supplier", options: recordOptions(suppliers, (s) => s.name, { any: "Any" }) });
    const fBranch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "ID", value: (o) => String(o.id) },
        { label: "Supplier", value: (o) => supplierName(o.supplier_id) },
        { label: "Branch", value: (o) => branchName(map, o.branch_id) },
        { label: "Status", value: (o) => words(o.status) },
        { label: "Ordered on", value: (o) => fmtDate(o.ordered_on) },
        {
          label: "Lines",
          value: (o) =>
            h(
              "ul",
              { class: "order-lines" },
              o.lines.map((l) => h("li", {}, `${l._book.title} (${l._book.isbn}): ${l.received_quantity} of ${l.quantity} received, ${fmtAmount(l.unit_price)} each`)),
            ),
        },
        { label: "Total", value: (o) => fmtAmount(o.total) },
        { label: "Actions", value: (o) => orderActions(o) },
      ],
      load: async (page) => {
        const data = await get("/purchase-orders", { page, page_size: 20, status: fStatus.input.value, supplier_id: fSupplier.input.value, branch_id: fBranch.input.value });
        await Promise.all(
          data.items.flatMap((o) =>
            o.lines.map(async (l) => {
              l._book = await ctx.book(l.book_id);
            }),
          ),
        );
        return data;
      },
    });
    const reload = () => list.reload();

    function orderActions(order) {
      const buttons = [];
      if (order.status === "draft") {
        buttons.push(button("Edit", () => openEditor(order)));
        buttons.push(
          button("Submit", () => ctx.act(() => post(`/purchase-orders/${order.id}/submit`), `Order ${order.id} submitted.`, reload)),
        );
      }
      if (order.status === "draft" || (order.status === "ordered")) {
        buttons.push(
          button("Cancel", () =>
            ctx.ask({
              text: `Cancel purchase order ${order.id}?`,
              onConfirm: () => ctx.act(() => post(`/purchase-orders/${order.id}/cancel`), `Order ${order.id} cancelled.`, reload),
            }),
          ),
        );
      }
      if ((order.status === "ordered" || order.status === "partially_received") && receiving === null) {
        buttons.push(button("Receive", () => openReceive(order)));
      }
      return buttons.length ? h("span", { class: "row-actions" }, buttons) : "–";
    }

    // -- editor for a new or an existing draft
    function openEditor(order = null) {
      const supplier = field({
        name: "supplier_id",
        label: "Supplier",
        options: recordOptions(suppliers.filter((s) => s.is_active || s.id === order?.supplier_id), (s) => s.name),
        value: order?.supplier_id,
      });
      const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { activeOnly: true }), value: order?.branch_id });
      const linesBody = h("tbody");
      const addLine = (data = {}) => {
        const isbn = field({ name: "isbn", label: "ISBN", value: data.isbn });
        const quantity = field({ name: "quantity", label: "Quantity", type: "number", value: data.quantity ?? "1", min: 1, max: 100 });
        const price = field({ name: "unit_price", label: "Unit price", inputmode: "decimal", value: data.unit_price });
        const row = h(
          "tr",
          { class: "line" },
          h("td", { "data-label": "ISBN" }, isbn),
          h("td", { "data-label": "Quantity" }, quantity),
          h("td", { "data-label": "Unit price" }, price),
          h("td", { "data-label": "Actions" }, button("Remove line", () => row.remove())),
        );
        row.read = () => ({ isbn: isbn.input.value, quantity: quantity.input.value, unit_price: price.input.value });
        linesBody.append(row);
      };
      if (order) {
        for (const l of order.lines) addLine({ isbn: l._book.isbn, quantity: l.quantity, unit_price: l.unit_price });
      } else {
        addLine();
      }
      const linesTable = h(
        "div",
        { class: "table-wrap" },
        h("table", { class: "lines-table" }, h("thead", {}, h("tr", {}, ["ISBN", "Quantity", "Unit price", "Actions"].map((t) => h("th", { scope: "col" }, t)))), linesBody),
      );
      const node = form({
        fields: [supplier, branch, h("fieldset", { class: "lines" }, h("legend", {}, "Lines"), linesTable, button("Add line", () => addLine()))],
        submit: order ? "Save" : "Create",
        label: order ? "Change draft" : "Create draft",
        extra: button("Close", () => replace(editor)),
        async onSubmit(v) {
          const done = await ctx.act(
            async () => {
              const lines = [];
              for (const row of linesBody.querySelectorAll("tr.line")) {
                const line = row.read();
                if (!line.isbn.trim() && !line.unit_price.trim()) continue;
                const book = await findBook(line.isbn);
                lines.push({ book_id: book.id, quantity: int(line.quantity), unit_price: line.unit_price.trim() });
              }
              const body = { supplier_id: Number(v.supplier_id), branch_id: Number(v.branch_id), lines };
              return order ? patch(`/purchase-orders/${order.id}`, body) : post("/purchase-orders", body);
            },
            (o) => (order ? `Order ${o.id} saved.` : `Draft order ${o.id} created. Total: ${fmtAmount(o.total)}`),
            async () => {
              await reload();
              replace(editor);
            },
          );
          return done;
        },
      });
      replace(editor, section(order ? `Change draft ${order.id}` : "New draft order", node));
      editor.scrollIntoView?.({ block: "nearest" });
    }

    // -- receiving
    function openReceive(order) {
      receiving = order.id;
      const areas = order.lines.map((l) => {
        const barcodes = field({
          name: "barcodes",
          label: `Barcodes for ${l._book.title} (${l.quantity - l.received_quantity} still expected)`,
          type: "textarea",
          hint: "One barcode per line.",
          rows: 3,
        });
        const count = h("small", { class: "count" }, "Received quantity: 0");
        barcodes.input.addEventListener("input", () => {
          count.textContent = `Received quantity: ${barcodesOf(barcodes.input.value).length}`;
        });
        return { line: l, barcodes, count };
      });
      const node = form({
        fields: areas.map((a) => h("div", { class: "receive-line" }, a.barcodes, a.count)),
        submit: "Receive",
        label: "Receive an order",
        extra: button("Back", closeReceive),
        async onSubmit() {
          const lines = areas
            .map((a) => ({ line_id: a.line.id, barcodes: barcodesOf(a.barcodes.input.value) }))
            .filter((l) => l.barcodes.length);
          const done = await ctx.act(
            () => post(`/purchase-orders/${order.id}/receive`, { lines }),
            (o) => `Order ${o.id} received: status ${words(o.status)}.`,
            async () => {
              receiving = null;
              replace(receivePanel);
              await reload();
            },
          );
          return done;
        },
      });
      replace(receivePanel, section(`Receive order ${order.id}`, node));
      reload();
    }
    function closeReceive() {
      receiving = null;
      replace(receivePanel);
      reload();
    }
    const barcodesOf = (value) => value.split(/[\s,;]+/).map((b) => b.trim()).filter(Boolean);

    const filters = form({
      fields: [fStatus, fSupplier, fBranch],
      submit: "Filter",
      label: "Order filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    replace(
      ctx.body,
      h("div", { class: "actions" }, button("New order", () => openEditor())),
      editor,
      receivePanel,
      section("Order list", filters, list.el),
    );
    await list.goTo(1);
  },
};

// ---- LIB-UI-AUD-01 ---------------------------------------------------------------

const auditScreen = {
  id: "aud-01",
  title: "Audit log",
  module: "Audit log and data",
  roles: ["admin"],
  desk: true,
  async render(ctx) {
    const event = field({ name: "event", label: "Event" });
    const actor = field({ name: "actor_user_id", label: "Actor user ID", type: "number", min: 1 });
    const entityType = field({ name: "entity_type", label: "Entity type" });
    const entityId = field({ name: "entity_id", label: "Entity ID", type: "number", min: 1 });
    const from = field({ name: "from", label: "From", type: "date" });
    const to = field({ name: "to", label: "To", type: "date" });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "ID", value: (a) => String(a.id) },
        { label: "Time", value: (a) => fmtDateTime(a.at) },
        { label: "Actor", value: (a) => fmtText(a.actor_user_id) },
        { label: "Event", value: (a) => a.event },
        { label: "Entity", value: (a) => a.entity_type },
        { label: "Entity ID", value: (a) => fmtText(a.entity_id) },
        { label: "Details", value: (a) => h("code", { class: "details" }, JSON.stringify(a.details)) },
      ],
      load: (page) =>
        get("/audit-log", {
          page,
          page_size: 20,
          event: event.input.value.trim(),
          actor_user_id: actor.input.value.trim(),
          entity_type: entityType.input.value.trim(),
          entity_id: entityId.input.value.trim(),
          from: from.input.value,
          to: to.input.value,
        }),
    });
    const filters = form({
      fields: [event, actor, entityType, entityId, from, to],
      submit: "Filter",
      label: "Audit filters",
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

// ---- LIB-UI-AUD-02 ---------------------------------------------------------------

const CSV_ENTITIES = ["branches", "books", "copies", "members", "loans"];

const dataScreen = {
  id: "aud-02",
  title: "Import and export",
  module: "Audit log and data",
  roles: ["admin"],
  desk: true,
  async render(ctx) {
    const result = h("div", { class: "import-result" });
    const file = field({ name: "file", label: "JSON file", type: "file", accept: ".json,application/json" });
    const importForm = form({
      fields: [file],
      submit: "Import",
      label: "Import data",
      async onSubmit() {
        replace(result);
        const chosen = file.input.files?.[0];
        if (!chosen) {
          ctx.fail(clientError("VALIDATION_ERROR", "Choose a JSON file first.", { fields: [{ field: "file", problem: "field required" }] }));
          return;
        }
        const content = await chosen.text();
        const done = await ctx.act(
          () => api("POST", "/import", { rawBody: content }),
          (r) => `Import finished: ${Object.entries(r.imported).map(([k, n]) => `${n} ${k}`).join(", ")}.`,
        );
        if (done) {
          replace(
            result,
            table({
              columns: [
                { label: "Records", value: (r) => r[0] },
                { label: "Imported", value: (r) => String(r[1]) },
              ],
              rows: Object.entries(done.imported),
            }),
          );
        }
      },
    });
    const exportButton = button("Export", () =>
      ctx.act(() => download("/export", "lms-export.json"), "Export downloaded."),
    );
    const links = h(
      "ul",
      { class: "csv-links" },
      CSV_ENTITIES.map((entity) =>
        h(
          "li",
          {},
          h(
            "a",
            {
              href: `/api/v1/export/${entity}.csv`,
              download: `${entity}.csv`,
              onclick: (event) => {
                event.preventDefault();
                ctx.act(() => download(`/export/${entity}.csv`, `${entity}.csv`), `${entity}.csv downloaded.`);
              },
            },
            `${entity}.csv`,
          ),
        ),
      ),
    );
    replace(
      ctx.body,
      section("Import", importForm, result),
      section("Export", h("div", { class: "actions" }, exportButton), links),
    );
  },
};

export const adminScreens = [branchesScreen, transfersScreen, suppliersScreen, ordersScreen, auditScreen, dataScreen];
