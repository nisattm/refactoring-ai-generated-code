// Module 25: purchase suggestions (LIB-UI-SUG-01 to LIB-UI-SUG-06).

import { del, fetchAll, get, post, patch } from "../api.js";
import { findBook } from "../context.js";
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
  text,
  words,
} from "../ui.js";
import { branchMap, branchName, memberLink, withMembers } from "../views.js";

const MODULE = "Purchase suggestions";
const STATUSES = ["submitted", "approved", "ordered", "available", "rejected", "withdrawn", "merged", "expired"];
const REJECT_REASONS = ["already_owned", "out_of_scope", "too_expensive", "not_available", "other"];
const OPEN = new Set(["submitted", "approved", "ordered"]);

// ---- helpers ---------------------------------------------------------------------

const suggestionLink = (id, label) => link(label ?? `#${id}`, `#/sug-02/${id}`);

/** Adds a link to the alert that is shown (LIB-UI-SUG-01: the answers link to the book or the suggestion). */
function addAlertLink(ctx, prefix, href, label) {
  const alert = ctx.messages.querySelector('[role="alert"]');
  if (alert) alert.append(h("p", { class: "error-link" }, prefix, link(label, href)));
}

function titleCell(s) {
  return h("span", { class: "sug-title" }, h("strong", {}, s.title), s.author_text ? h("br") : null, s.author_text || null);
}

const priceCell = (s) => (s.quantity ? `${s.quantity} × ${fmtAmount(s.estimated_price)}` : "–");

/** Rules text of 33.2, shown to the member who suggests. */
const RULES_TEXT =
  "Open suggestions at a time: students 3, academic members 10, staff 5. Guests cannot suggest. " +
  "A book that the library already lends cannot be suggested again.";

async function myMember() {
  return get("/members/me");
}

function bookOptionLabel(book) {
  return `${book.title} (${book.isbn})`;
}

/** Search the catalog (GET /search/books) and let the user pick one book: onChoose(book). */
function catalogSearch(ctx, { initial, onChoose }) {
  const q = field({ name: "q", label: "Search the catalog", value: initial || "", hint: "Title, author or ISBN." });
  const results = pagedTable({
    onError: (e) => ctx.fail(e),
    columns: [
      { label: "Title", value: (r) => r.book.title },
      { label: "Authors", value: (r) => (r.book.authors.length ? r.book.authors.map((a) => a.name).join(", ") : "–") },
      { label: "ISBN", value: (r) => r.book.isbn },
      { label: "Year", value: (r) => String(r.book.publication_year) },
      { label: "Actions", value: (r) => button("Choose", () => onChoose(r.book)) },
    ],
    load: (page) => get("/search/books", { page, page_size: 5, q: q.input.value.trim() }),
  });
  const box = h("div", { class: "book-results" });
  const node = form({
    fields: [q],
    submit: "Search",
    label: "Search the catalog",
    cls: "filters",
    onSubmit() {
      ctx.clearMessages();
      replace(box, results.el);
      return results.goTo(1);
    },
  });
  return {
    el: h("div", { class: "catalog-search" }, node, box),
    run: () => {
      replace(box, results.el);
      return results.goTo(1);
    },
  };
}

// ---- LIB-UI-SUG-01 ---------------------------------------------------------------

const suggestScreen = {
  id: "sug-01",
  title: "Suggest a book",
  module: MODULE,
  roles: ["member"],
  async render(ctx) {
    const me = await myMember();
    const branches = (await ctx.branches()).filter((b) => b.is_active);
    const title = field({ name: "title", label: "Title", required: true, hint: "1–300 characters." });
    const author = field({ name: "author_text", label: "Author", hint: "Up to 200 characters." });
    const isbn = field({ name: "isbn", label: "ISBN", hint: "ISBN-10 or ISBN-13; optional." });
    const year = field({
      name: "publication_year",
      label: "Year",
      type: "number",
      min: 1450,
      hint: "Year of publication; optional.",
    });
    const reason = field({ name: "reason", label: "Reason", type: "textarea", rows: 3, hint: "Up to 500 characters." });
    const branch = field({
      name: "branch_id",
      label: "Branch",
      options: branchOptions(branches),
      value: branches.some((b) => b.id === me.home_branch_id) ? me.home_branch_id : undefined,
      hint: "Where you want to collect the book.",
    });
    const resultBox = h("div", { class: "suggest-result" });

    const node = form({
      fields: [title, author, isbn, year, reason, branch],
      submit: "Suggest",
      label: "Suggest a book",
      async onSubmit(v) {
        node.fieldErrors({});
        replace(resultBox);
        const body = {
          title: v.title.trim(),
          author_text: v.author_text.trim(),
          isbn: text(v.isbn),
          publication_year: int(v.publication_year),
          reason: v.reason.trim(),
          branch_id: int(v.branch_id),
        };
        await ctx.act(
          () => post("/suggestions", body),
          (s) => `Suggestion ${s.id} submitted.`,
          (s) => {
            for (const f of [title, author, isbn, year, reason]) f.input.value = "";
            replace(
              resultBox,
              section(
                "Your suggestion",
                definitionList([
                  ["Number", String(s.id)],
                  ["Title", s.title],
                  ["Status", s.status],
                  ["Score", String(s.score)],
                  ["Submitted", fmtDate(s.submitted_at)],
                ]),
                h("p", {}, link("My suggestions", "#/sug-03"), " · ", link("Suggestions board", `#/sug-02/${s.id}`)),
              ),
            );
          },
          (error) => {
            node.fieldErrors(fieldProblems(error));
            const d = error.details || {};
            if (error.code === "BOOK_ALREADY_OWNED" && d.book_id) {
              addAlertLink(ctx, "The library already owns this book: ", `#/cat-02/${d.book_id}`, "open the book");
            } else if (error.code === "DUPLICATE_SUGGESTION" && d.suggestion_id) {
              addAlertLink(ctx, "This book is already suggested: ", `#/sug-02/${d.suggestion_id}`, "open the suggestion");
            }
          },
        );
      },
    });
    replace(ctx.body, h("p", { class: "hint" }, RULES_TEXT), node, resultBox);
  },
};

// ---- LIB-UI-SUG-02 ---------------------------------------------------------------

function supportCell(ctx, s, reload) {
  if (s.mine) return "Your suggestion";
  if (s.supported_by_me) {
    return button("Stop supporting", () =>
      ctx.act(() => del(`/suggestions/${s.id}/support`), `You no longer support suggestion ${s.id}.`, reload),
    );
  }
  if (!OPEN.has(s.status)) return "–";
  const reserve = h("input", { type: "checkbox", name: "reserve_on_arrival", checked: true });
  return h(
    "div",
    { class: "support-cell" },
    h("label", { class: "check" }, reserve, " Reserve when it arrives"),
    button("Support", () =>
      ctx.act(
        () => post(`/suggestions/${s.id}/support`, { reserve_on_arrival: reserve.checked }),
        `You support suggestion ${s.id}.`,
        reload,
      ),
    ),
  );
}

const boardScreen = {
  id: "sug-02",
  title: "Suggestions board",
  module: MODULE,
  roles: ["all"],
  async render(ctx) {
    const map = await branchMap(ctx);
    const branches = await ctx.branches();
    const q = field({ name: "q", label: "Search title or author" });
    const isbn = field({ name: "isbn", label: "ISBN" });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const status = ctx.isStaff ? field({ name: "status", label: "Status", options: choices(STATUSES, { any: "Any" }) }) : null;
    const detailBox = h("div", { class: "suggestion-detail" });
    const focusId = /^\d+$/.test(ctx.param) ? Number(ctx.param) : null;

    const columns = () => {
      const list = [
        { label: "ID", value: (s) => String(s.id) },
        { label: "Score", value: (s) => String(s.score) },
        { label: "Title", value: (s) => titleCell(s) },
        { label: "ISBN", value: (s) => fmtText(s.isbn) },
        { label: "Year", value: (s) => fmtText(s.publication_year) },
        { label: "Branch", value: (s) => branchName(map, s.branch_id) },
        { label: "Supporters", value: (s) => String(s.supporters) },
        { label: "Status", value: (s) => s.status },
        { label: "Reason", value: (s) => fmtText(s.reason) },
      ];
      if (ctx.isStaff) {
        list.splice(
          2,
          0,
          { label: "Member", value: (s) => (s._member ? memberLink(s._member) : fmtText(s.member_id)) },
        );
      }
      if (ctx.isMember) list.push({ label: "Actions", value: (s) => supportCell(ctx, s, reloadAll) });
      return list;
    };

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      rowClass: (s) => (s.id === focusId ? "focused" : undefined),
      columns: columns(),
      async load(page) {
        const data = await get("/suggestions", {
          page,
          page_size: 20,
          q: q.input.value.trim(),
          isbn: isbn.input.value.trim(),
          branch_id: branch.input.value,
          status: status ? status.input.value : "",
        });
        if (ctx.isStaff) await withMembers(ctx, data.items).catch(() => {});
        return data;
      },
    });

    async function loadDetail() {
      if (focusId === null) return;
      try {
        const s = await get(`/suggestions/${focusId}`);
        if (ctx.isStaff) await withMembers(ctx, [s]).catch(() => {});
        replace(detailBox, section(`Suggestion ${focusId}`, table({ columns: columns(), rows: [s] })));
      } catch (error) {
        replace(detailBox);
        ctx.fail(error);
      }
    }

    async function reloadAll() {
      await Promise.all([list.reload(), loadDetail()]);
    }

    const node = form({
      fields: [q, isbn, branch, ...(status ? [status] : [])],
      submit: "Search",
      label: "Suggestion filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return list.goTo(1);
      },
    });
    replace(
      ctx.body,
      ctx.isStaff ? null : h("p", { class: "hint" }, "Open suggestions, the highest score first. Suggestions are anonymous."),
      node,
      detailBox,
      list.el,
    );
    await Promise.all([list.goTo(1), loadDetail()]);
  },
};

// ---- LIB-UI-SUG-03 ---------------------------------------------------------------

const mySuggestionsScreen = {
  id: "sug-03",
  title: "My suggestions",
  module: "Purchase suggestions",
  roles: ["member"],
  async render(ctx) {
    const me = await myMember();
    const map = await branchMap(ctx);
    const branches = await ctx.branches();
    const ownBox = h("div", { class: "own-suggestions" });
    const supportedBox = h("div", { class: "supported-suggestions" });
    const editBox = h("div", { class: "edit-suggestion" });

    function openEdit(s) {
      const title = field({ name: "title", label: "Title", value: s.title });
      const author = field({ name: "author_text", label: "Author", value: s.author_text });
      const isbn = field({ name: "isbn", label: "ISBN", value: s.isbn || "" });
      const year = field({ name: "publication_year", label: "Year", type: "number", min: 1450, value: s.publication_year ?? "" });
      const reason = field({ name: "reason", label: "Reason", type: "textarea", rows: 3, value: s.reason });
      const branch = field({
        name: "branch_id",
        label: "Branch",
        options: branchOptions(branches.filter((b) => b.is_active || b.id === s.branch_id)),
        value: s.branch_id,
      });
      const node = form({
        fields: [title, author, isbn, year, reason, branch],
        submit: "Save",
        label: "Change suggestion",
        extra: button("Close", () => replace(editBox)),
        async onSubmit(v) {
          node.fieldErrors({});
          const body = {};
          if (v.title.trim() !== s.title) body.title = v.title.trim();
          if (v.author_text.trim() !== s.author_text) body.author_text = v.author_text.trim();
          const newIsbn = text(v.isbn);
          if (newIsbn !== s.isbn) body.isbn = newIsbn;
          const newYear = int(v.publication_year);
          if (newYear !== s.publication_year) body.publication_year = newYear;
          if (v.reason.trim() !== s.reason) body.reason = v.reason.trim();
          if (int(v.branch_id) !== s.branch_id) body.branch_id = int(v.branch_id);
          if (!Object.keys(body).length) {
            ctx.clearMessages();
            ctx.ok("Nothing was changed.");
            return;
          }
          await ctx.act(
            () => patch(`/suggestions/${s.id}`, body),
            `Suggestion ${s.id} changed.`,
            async () => {
              replace(editBox);
              await load();
            },
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      replace(editBox, section(`Change suggestion ${s.id}`, node));
      title.input.focus();
    }

    function askWithdraw(s) {
      ctx.ask({
        text: `Withdraw suggestion ${s.id} "${s.title}"?`,
        onConfirm: () =>
          ctx.act(
            () => post(`/suggestions/${s.id}/withdraw`),
            `Suggestion ${s.id} withdrawn.`,
            async () => {
              replace(editBox);
              await load();
            },
          ),
      });
    }

    const statusCell = (s) => (s.status === "rejected" && s.reject_reason ? `rejected (${words(s.reject_reason)})` : s.status);
    const ownColumns = [
      { label: "ID", value: (s) => String(s.id) },
      { label: "Title", value: (s) => titleCell(s) },
      { label: "ISBN", value: (s) => fmtText(s.isbn) },
      { label: "Branch", value: (s) => branchName(map, s.branch_id) },
      { label: "Status", value: (s) => statusCell(s) },
      { label: "Review note", value: (s) => fmtText(s.review_note) },
      { label: "Approved for", value: (s) => priceCell(s) },
      { label: "Score", value: (s) => String(s.score) },
      { label: "Supporters", value: (s) => String(s.supporters) },
      { label: "Submitted", value: (s) => fmtDate(s.submitted_at) },
      { label: "Reviewed", value: (s) => fmtDate(s.reviewed_at) },
      { label: "Available", value: (s) => fmtDate(s.available_at) },
      {
        label: "Actions",
        value: (s) =>
          s.status === "submitted"
            ? h("div", { class: "row-actions" }, button("Change", () => openEdit(s)), button("Withdraw", () => askWithdraw(s)))
            : "–",
      },
    ];
    const supportedColumns = [
      { label: "ID", value: (s) => suggestionLink(s.id, String(s.id)) },
      { label: "Title", value: (s) => titleCell(s) },
      { label: "Branch", value: (s) => branchName(map, s.branch_id) },
      { label: "Status", value: (s) => s.status },
      { label: "Score", value: (s) => String(s.score) },
      { label: "Supporters", value: (s) => String(s.supporters) },
      {
        label: "Actions",
        value: (s) =>
          button("Stop supporting", () =>
            ctx.act(() => del(`/suggestions/${s.id}/support`), `You no longer support suggestion ${s.id}.`, load),
          ),
      },
    ];

    async function load() {
      const data = await get(`/members/${me.id}/suggestions`);
      replace(
        ownBox,
        section("Suggestions I made", table({ columns: ownColumns, rows: data.own })),
      );
      replace(supportedBox, section("Suggestions I support", table({ columns: supportedColumns, rows: data.supported })));
    }

    replace(ctx.body, ownBox, editBox, supportedBox);
    await load();
  },
};

// ---- LIB-UI-SUG-04 ---------------------------------------------------------------

const reviewScreen = {
  id: "sug-04",
  title: "Review queue",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const map = await branchMap(ctx);
    const branches = await ctx.branches();
    const panelBox = h("div", { class: "review-panel" });

    const q = field({ name: "q", label: "Search title or author" });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const status = field({
      name: "status",
      label: "Status",
      options: choices(["submitted", "approved"]),
      value: "submitted",
    });

    const closePanel = () => replace(panelBox);
    const afterAction = async () => {
      closePanel();
      await list.reload();
    };

    // -- approve (LIB-SUG-15)
    function approvePanel(s) {
      const isbn = field({
        name: "isbn",
        label: "Book ISBN",
        value: s.isbn || "",
        hint: "Choose the book in the catalog search below, or enter its ISBN.",
      });
      const quantity = field({ name: "quantity", label: "Quantity", type: "number", min: 1, max: 10, value: "1", hint: "1–10 copies." });
      const price = field({
        name: "estimated_price",
        label: "Estimated price per copy",
        inputmode: "decimal",
        hint: "0.01–5000.00 TL. A total above 300.00 TL can only be approved by an admin.",
      });
      const note = field({ name: "review_note", label: "Review note", type: "textarea", rows: 2, hint: "Optional, up to 500 characters." });
      const chosen = h("p", { class: "chosen-book" });
      const node = form({
        fields: [isbn, quantity, price, note],
        submit: "Approve",
        label: "Approve suggestion",
        extra: button("Close", closePanel),
        async onSubmit(v) {
          node.fieldErrors({});
          ctx.clearMessages();
          let book;
          try {
            book = await findBook(v.isbn);
          } catch (error) {
            ctx.fail(error);
            node.fieldErrors(fieldProblems(error));
            return;
          }
          await ctx.act(
            () =>
              post(`/suggestions/${s.id}/approve`, {
                book_id: book.id,
                quantity: int(v.quantity),
                estimated_price: v.estimated_price.trim(),
                review_note: v.review_note.trim(),
              }),
            `Suggestion ${s.id} approved for "${book.title}".`,
            afterAction,
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      const search = catalogSearch(ctx, {
        initial: s.isbn || s.title,
        onChoose(book) {
          isbn.input.value = book.isbn;
          replace(chosen, "Chosen book: ", link(book.title, `#/cat-02/${book.id}`), ` (${book.isbn})`);
          quantity.input.focus();
        },
      });
      replace(
        panelBox,
        section(
          `Approve suggestion ${s.id}: ${s.title}`,
          h("p", { class: "hint" }, `Branch ${branchName(map, s.branch_id)}. ${s.isbn ? `ISBN ${s.isbn}.` : "The suggestion has no ISBN."}`),
          node,
          chosen,
          search.el,
        ),
      );
      isbn.input.focus();
      return search.run();
    }

    // -- reject (LIB-SUG-17, LIB-SUG-18)
    function rejectPanel(s) {
      const reason = field({
        name: "reject_reason",
        label: "Reason",
        options: choices(REJECT_REASONS),
        value: "out_of_scope",
      });
      const isbn = field({
        name: "isbn",
        label: "ISBN of the owned book",
        value: s.isbn || "",
        hint: "The member and the supporters who asked for it get a reservation of this book.",
      });
      const note = field({ name: "review_note", label: "Review note", type: "textarea", rows: 2, hint: "Optional, up to 500 characters." });
      const toggle = () => {
        isbn.hidden = reason.input.value !== "already_owned";
      };
      reason.input.addEventListener("change", toggle);
      toggle();
      const node = form({
        fields: [reason, isbn, note],
        submit: "Reject",
        label: "Reject suggestion",
        extra: button("Close", closePanel),
        async onSubmit(v) {
          node.fieldErrors({});
          ctx.clearMessages();
          const body = { reject_reason: v.reject_reason, review_note: v.review_note.trim() };
          if (v.reject_reason === "already_owned") {
            try {
              body.book_id = (await findBook(v.isbn)).id;
            } catch (error) {
              ctx.fail(error);
              node.fieldErrors(fieldProblems(error));
              return;
            }
          }
          await ctx.act(
            () => post(`/suggestions/${s.id}/reject`, body),
            `Suggestion ${s.id} rejected.`,
            afterAction,
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      replace(panelBox, section(`Reject suggestion ${s.id}: ${s.title}`, node));
      reason.input.focus();
    }

    // -- merge (LIB-SUG-22)
    function mergePanel(s) {
      const target = field({
        name: "into_suggestion_id",
        label: "Merge into suggestion",
        type: "number",
        min: 1,
        hint: "The number of the suggestion that stays; choose it below or type it.",
      });
      const node = form({
        fields: [target],
        submit: "Merge",
        label: "Merge suggestion",
        extra: button("Close", closePanel),
        async onSubmit(v) {
          node.fieldErrors({});
          await ctx.act(
            () => post(`/suggestions/${s.id}/merge`, { into_suggestion_id: int(v.into_suggestion_id) }),
            (t) => `Suggestion ${s.id} merged into suggestion ${t.id}.`,
            afterAction,
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      const q = field({ name: "q", label: "Search candidates", hint: "Leave empty to list the open suggestions by score." });
      const candidates = pagedTable({
        onError: (e) => ctx.fail(e),
        columns: [
          { label: "ID", value: (t) => String(t.id) },
          { label: "Title", value: (t) => titleCell(t) },
          { label: "ISBN", value: (t) => fmtText(t.isbn) },
          { label: "Branch", value: (t) => branchName(map, t.branch_id) },
          { label: "Score", value: (t) => String(t.score) },
          { label: "Status", value: (t) => t.status },
          {
            label: "Actions",
            value: (t) =>
              t.id === s.id
                ? "This suggestion"
                : t.status === "submitted" || t.status === "approved"
                  ? button("Choose", () => {
                      target.input.value = String(t.id);
                      target.input.focus();
                    })
                  : "–",
          },
        ],
        load: (page) => get("/suggestions", { page, page_size: 5, q: q.input.value.trim() }),
      });
      const searchForm = form({
        fields: [q],
        submit: "Search",
        label: "Search candidates",
        cls: "filters",
        onSubmit() {
          ctx.clearMessages();
          return candidates.goTo(1);
        },
      });
      replace(panelBox, section(`Merge suggestion ${s.id}: ${s.title}`, node, searchForm, candidates.el));
      target.input.focus();
      return candidates.goTo(1);
    }

    // -- change an approval (LIB-SUG-24)
    function approvalPanel(s) {
      const quantity = field({ name: "quantity", label: "Quantity", type: "number", min: 1, max: 10, value: s.quantity ?? "" });
      const price = field({
        name: "estimated_price",
        label: "Estimated price per copy",
        inputmode: "decimal",
        value: s.estimated_price ?? "",
        hint: "0.01–5000.00 TL. A total above 300.00 TL can only be approved by an admin.",
      });
      const note = field({ name: "review_note", label: "Review note", type: "textarea", rows: 2, value: s.review_note });
      const node = form({
        fields: [quantity, price, note],
        submit: "Save",
        label: "Change approval",
        extra: button("Close", closePanel),
        async onSubmit(v) {
          node.fieldErrors({});
          const body = {};
          if (int(v.quantity) !== s.quantity) body.quantity = int(v.quantity);
          if (v.estimated_price.trim() !== s.estimated_price) body.estimated_price = v.estimated_price.trim();
          if (v.review_note.trim() !== s.review_note) body.review_note = v.review_note.trim();
          if (!Object.keys(body).length) {
            ctx.clearMessages();
            ctx.ok("Nothing was changed.");
            return;
          }
          await ctx.act(
            () => patch(`/suggestions/${s.id}/approval`, body),
            `Approval of suggestion ${s.id} changed.`,
            afterAction,
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      replace(panelBox, section(`Change approval of suggestion ${s.id}: ${s.title}`, node));
      quantity.input.focus();
    }

    // -- supporters (LIB-SUG-10)
    function supportersPanel(s) {
      const supporters = pagedTable({
        onError: (e) => ctx.fail(e),
        columns: [
          { label: "Member", value: (r) => (r._member ? memberLink(r._member) : `#${r.member_id}`) },
          { label: "Name", value: (r) => r.full_name },
          { label: "Membership type", value: (r) => r.membership_type },
          { label: "Reserve when it arrives", value: (r) => fmtBool(r.reserve_on_arrival) },
          { label: "Supporting since", value: (r) => fmtDate(r.created_at) },
        ],
        async load(page) {
          const data = await get(`/suggestions/${s.id}/supporters`, { page, page_size: 20 });
          await withMembers(ctx, data.items).catch(() => {});
          return data;
        },
      });
      replace(
        panelBox,
        section(`Supporters of suggestion ${s.id}: ${s.title}`, supporters.el, h("div", { class: "actions" }, button("Close", closePanel))),
      );
      return supporters.goTo(1);
    }

    // -- withdraw (staff, approved; LIB-SUG-06)
    function askWithdraw(s) {
      ctx.ask({
        text: `Withdraw suggestion ${s.id} "${s.title}"?`,
        onConfirm: () => ctx.act(() => post(`/suggestions/${s.id}/withdraw`), `Suggestion ${s.id} withdrawn.`, afterAction),
      });
    }

    const rowActions = (s) => {
      const buttons = [];
      if (s.status === "submitted") {
        buttons.push(button("Approve", () => approvePanel(s)), button("Reject", () => rejectPanel(s)), button("Merge", () => mergePanel(s)));
      } else if (s.status === "approved") {
        buttons.push(
          button("Change approval", () => approvalPanel(s)),
          button("Reject", () => rejectPanel(s)),
          button("Withdraw", () => askWithdraw(s)),
        );
      }
      buttons.push(button("Supporters", () => supportersPanel(s)));
      return h("div", { class: "row-actions" }, buttons);
    };

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "ID", value: (s) => String(s.id) },
        { label: "Score", value: (s) => String(s.score) },
        { label: "Title", value: (s) => titleCell(s) },
        { label: "Member", value: (s) => (s._member ? memberLink(s._member) : fmtText(s.member_id)) },
        { label: "ISBN", value: (s) => fmtText(s.isbn) },
        { label: "Year", value: (s) => fmtText(s.publication_year) },
        { label: "Branch", value: (s) => branchName(map, s.branch_id) },
        { label: "Supporters", value: (s) => String(s.supporters) },
        { label: "Reason", value: (s) => fmtText(s.reason) },
        { label: "Status", value: (s) => s.status },
        { label: "Approved for", value: (s) => priceCell(s) },
        { label: "Review note", value: (s) => fmtText(s.review_note) },
        { label: "Submitted", value: (s) => fmtDate(s.submitted_at) },
        { label: "Actions", value: (s) => rowActions(s) },
      ],
      async load(page) {
        const data = await get("/suggestions", {
          page,
          page_size: 20,
          status: status.input.value,
          branch_id: branch.input.value,
          q: q.input.value.trim(),
        });
        await withMembers(ctx, data.items).catch(() => {});
        return data;
      },
    });

    const filters = form({
      fields: [status, branch, q],
      submit: "Filter",
      label: "Review filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        closePanel();
        return list.goTo(1);
      },
    });

    const process = button("Process expired", () =>
      ctx.act(
        () => post("/suggestions/process"),
        (r) => `${r.expired_submitted} submitted and ${r.expired_approved} approved suggestions expired.`,
        afterAction,
      ),
    );

    replace(ctx.body, filters, h("div", { class: "actions" }, process), panelBox, list.el);
    await list.goTo(1);
  },
};

// ---- LIB-UI-SUG-05 ---------------------------------------------------------------

const toCents = (amount) => Math.round(Number(amount) * 100);
const fromCents = (cents) => (cents / 100).toFixed(2);

const orderingScreen = {
  id: "sug-05",
  title: "Ordering",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = (await ctx.branches()).filter((b) => b.is_active);
    const suppliers = await fetchAll("/suppliers", { is_active: "true" });
    const supplier = field({
      name: "supplier_id",
      label: "Supplier",
      options: suppliers.length ? recordOptions(suppliers, (s) => s.name) : [{ value: "", label: "No active suppliers" }],
    });
    const branch = field({
      name: "branch_id",
      label: "Branch",
      options: branches.length ? branchOptions(branches) : [{ value: "", label: "No active branches" }],
    });
    const listBox = h("div", { class: "approved-list" });
    const previewBox = h("div", { class: "order-preview" });
    const resultBox = h("div", { class: "order-result" });
    let rows = [];
    let books = new Map();
    const selected = new Set();

    const orderButton = button("Create order", createOrder);
    orderButton.disabled = true;

    function previewLines() {
      const lines = new Map();
      for (const s of rows) {
        if (!selected.has(s.id)) continue;
        const line = lines.get(s.book_id) || { book_id: s.book_id, quantity: 0, cents: 0 };
        line.quantity += s.quantity;
        line.cents = Math.max(line.cents, toCents(s.estimated_price));
        lines.set(s.book_id, line);
      }
      return [...lines.values()];
    }

    function renderPreview() {
      orderButton.disabled = selected.size === 0;
      const lines = previewLines();
      const total = lines.reduce((sum, l) => sum + l.quantity * l.cents, 0);
      replace(
        previewBox,
        section(
          "Order preview",
          table({
            columns: [
              { label: "Book", value: (l) => (books.get(l.book_id) ? bookOptionLabel(books.get(l.book_id)) : `#${l.book_id}`) },
              { label: "Quantity", value: (l) => (l.quantity > 100 ? `${l.quantity} (at most 100 per line)` : String(l.quantity)) },
              { label: "Unit price", value: (l) => fmtAmount(fromCents(l.cents)) },
              { label: "Line total", value: (l) => fmtAmount(fromCents(l.quantity * l.cents)) },
            ],
            rows: lines,
          }),
          h("p", { class: "total" }, `Total: ${fmtAmount(fromCents(total))}`),
          h("div", { class: "actions" }, orderButton),
        ),
      );
    }

    function renderList() {
      const checkbox = (s) => {
        const box = h("input", { type: "checkbox", name: "suggestion_ids", value: String(s.id), checked: selected.has(s.id) });
        box.addEventListener("change", () => {
          if (box.checked) selected.add(s.id);
          else selected.delete(s.id);
          renderPreview();
        });
        return h("label", { class: "check" }, box, ` Select suggestion ${s.id}`);
      };
      replace(
        listBox,
        section(
          "Approved suggestions",
          table({
            columns: [
              { label: "Select", value: (s) => checkbox(s) },
              { label: "ID", value: (s) => String(s.id) },
              { label: "Title", value: (s) => titleCell(s) },
              { label: "Book", value: (s) => (books.get(s.book_id) ? bookOptionLabel(books.get(s.book_id)) : `#${s.book_id}`) },
              { label: "Quantity", value: (s) => String(s.quantity) },
              { label: "Estimated price", value: (s) => fmtAmount(s.estimated_price) },
              { label: "Score", value: (s) => String(s.score) },
              { label: "Approved", value: (s) => fmtDate(s.reviewed_at) },
            ],
            rows,
          }),
          h(
            "div",
            { class: "actions" },
            button("Select all", () => {
              for (const s of rows) selected.add(s.id);
              renderList();
              renderPreview();
            }),
            button("Select none", () => {
              selected.clear();
              renderList();
              renderPreview();
            }),
          ),
        ),
      );
    }

    async function load() {
      if (!branch.input.value) {
        rows = [];
        replace(listBox);
        replace(previewBox);
        return;
      }
      rows = await fetchAll("/suggestions", { status: "approved", branch_id: branch.input.value });
      const ids = [...new Set(rows.map((s) => s.book_id))];
      books = new Map();
      await Promise.all(
        ids.map(async (id) => {
          try {
            books.set(id, await ctx.book(id));
          } catch {
            // the id is shown instead of the title
          }
        }),
      );
      for (const id of [...selected]) if (!rows.some((s) => s.id === id)) selected.delete(id);
      renderList();
      renderPreview();
    }

    async function createOrder() {
      const ids = rows.filter((s) => selected.has(s.id)).map((s) => s.id);
      await ctx.act(
        () => post("/suggestions/order", { supplier_id: int(supplier.input.value), branch_id: int(branch.input.value), suggestion_ids: ids }),
        (o) => `Draft order ${o.id} created; total ${fmtAmount(o.total)}.`,
        async (o) => {
          selected.clear();
          replace(
            resultBox,
            section(
              `Order ${o.id}`,
              definitionList([
                ["Status", o.status],
                ["Supplier", suppliers.find((s) => s.id === o.supplier_id)?.name ?? `#${o.supplier_id}`],
                ["Branch", branches.find((b) => b.id === o.branch_id)?.name ?? `#${o.branch_id}`],
                ["Total", fmtAmount(o.total)],
                ["Suggestions", o.suggestion_ids.join(", ")],
              ]),
              table({
                columns: [
                  { label: "Book", value: (l) => (books.get(l.book_id) ? bookOptionLabel(books.get(l.book_id)) : `#${l.book_id}`) },
                  { label: "Quantity", value: (l) => String(l.quantity) },
                  { label: "Unit price", value: (l) => fmtAmount(l.unit_price) },
                ],
                rows: o.lines,
              }),
              h("p", {}, link("Purchase orders", "#/pur-02")),
            ),
          );
          await load();
        },
        () => load().catch(() => {}),
      );
    }

    const node = form({
      fields: [supplier, branch],
      submit: "Show approved suggestions",
      label: "Order filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        selected.clear();
        replace(resultBox);
        return load();
      },
    });
    branch.input.addEventListener("change", () => {
      selected.clear();
      load().catch((e) => ctx.fail(e));
    });
    replace(ctx.body, node, listBox, previewBox, resultBox);
    await load();
  },
};

// ---- LIB-UI-SUG-06 ---------------------------------------------------------------

const reportScreen = {
  id: "sug-06",
  title: "Suggestions report",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const from = field({ name: "from", label: "From", type: "date", value: `${ctx.today.slice(0, 4)}-01-01` });
    const to = field({ name: "to", label: "To", type: "date", value: ctx.today });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "All branches" }) });
    const out = h("div", { class: "report" });

    async function load() {
      ctx.clearMessages();
      let r;
      try {
        r = await get("/reports/suggestions", { from: from.input.value, to: to.input.value, branch_id: branch.input.value });
      } catch (error) {
        replace(out);
        ctx.fail(error);
        return;
      }
      const rows = [
        ["Submitted", r.submitted],
        ["Approved", r.approved],
        ...REJECT_REASONS.map((reason) => [`Rejected: ${words(reason)}`, r.rejected[reason]]),
        ["Ordered", r.ordered],
        ["Available", r.available],
        ["Withdrawn", r.withdrawn],
        ["Merged", r.merged],
        ["Expired", r.expired],
        ["Average days to available", r.average_days_to_available === null ? "–" : r.average_days_to_available],
      ];
      replace(
        out,
        section("Summary", table({ columns: [{ label: "Measure", value: (x) => x[0] }, { label: "Count", value: (x) => String(x[1]) }], rows })),
        section(
          "Top suggestions",
          table({
            columns: [
              { label: "Suggestion", value: (t) => suggestionLink(t.suggestion_id, String(t.suggestion_id)) },
              { label: "Title", value: (t) => t.title },
              { label: "Score", value: (t) => String(t.score) },
            ],
            rows: r.top,
          }),
        ),
      );
    }

    const node = form({
      fields: [from, to, branch],
      submit: "Show",
      label: "Suggestions report",
      cls: "filters",
      onSubmit: load,
    });
    replace(ctx.body, node, out);
    await load();
  },
};

export const suggestionScreens = [
  suggestScreen,
  boardScreen,
  mySuggestionsScreen,
  reviewScreen,
  orderingScreen,
  reportScreen,
];
