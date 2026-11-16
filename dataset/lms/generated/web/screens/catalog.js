// Module 4: books, copies, authors and publishers (plus module 9: search lives in discovery.js).

import { del, fetchAll, get, patch, post } from "../api.js";
import { findBook } from "../context.js";
import { bookPageParts } from "../registry.js";
import {
  branchOptions,
  button,
  choices,
  definitionList,
  field,
  fieldProblems,
  fmtAmount,
  fmtDate,
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

export const COPY_STATUSES = [
  "available",
  "on_loan",
  "on_hold",
  "in_transfer",
  "damaged",
  "lost",
  "withdrawn",
  "at_partner",
  "on_reserve",
  "in_repair",
  "missing",
];

export function availabilityText(book, map) {
  if (!book.availability.length) return "No copies";
  return book.availability.map((a) => `${branchName(map, a.branch_id)}: ${a.available} of ${a.total}`).join("; ");
}

export const authorNames = (book) => book.authors.map((a) => a.name).join(", ");

// ---- LIB-UI-CAT-01 ---------------------------------------------------------------

const booksScreen = {
  id: "cat-01",
  title: "Books",
  module: "Catalog",
  roles: ["all"],
  async render(ctx) {
    const map = await branchMap(ctx);
    const [authors, publishers] = await Promise.all([fetchAll("/authors"), fetchAll("/publishers")]);
    const isbn = field({ name: "isbn", label: "ISBN" });
    const author = field({ name: "author_id", label: "Author", options: recordOptions(authors, (a) => a.name, { any: "Any" }) });
    const publisher = field({ name: "publisher_id", label: "Publisher", options: recordOptions(publishers, (p) => p.name, { any: "Any" }) });
    const language = field({ name: "language", label: "Language", hint: "Two letters, for example tr." });
    const classification = field({ name: "classification_prefix", label: "Classification prefix" });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      onRowClick: (b) => ctx.navigate(`#/cat-02/${b.id}`),
      columns: [
        { label: "Title", value: (b) => link(b.title, `#/cat-02/${b.id}`) },
        { label: "Authors", value: (b) => authorNames(b) },
        { label: "Year", value: (b) => String(b.publication_year) },
        { label: "ISBN", value: (b) => b.isbn },
        { label: "Availability", value: (b) => availabilityText(b, map) },
      ],
      load: (page) =>
        get("/books", {
          page,
          page_size: 20,
          isbn: isbn.input.value.trim(),
          author_id: author.input.value,
          publisher_id: publisher.input.value,
          language: language.input.value.trim(),
          classification_prefix: classification.input.value.trim(),
        }),
    });
    const filters = form({
      fields: [isbn, author, publisher, language, classification],
      submit: "Filter",
      label: "Book filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    replace(
      ctx.body,
      ctx.isStaff ? h("div", { class: "actions" }, button("New book", () => ctx.navigate("#/cat-03"))) : null,
      filters,
      list.el,
    );
    await list.goTo(1);
  },
};

// ---- LIB-UI-CAT-02 ---------------------------------------------------------------

const bookPageScreen = {
  id: "cat-02",
  title: "Book page",
  module: "Catalog",
  roles: ["all"],
  async render(ctx) {
    const id = /^\d+$/.test(ctx.param) ? Number(ctx.param) : null;
    if (id === null) {
      const isbn = field({ name: "isbn", label: "ISBN" });
      replace(
        ctx.body,
        form({
          fields: [isbn],
          submit: "Open",
          label: "Choose a book",
          async onSubmit(v) {
            ctx.clearMessages();
            try {
              const book = await findBook(v.isbn);
              ctx.navigate(`#/cat-02/${book.id}`);
            } catch (error) {
              ctx.fail(error);
            }
          },
        }),
      );
      return;
    }
    const map = await branchMap(ctx);
    const branches = await ctx.branches();
    const info = h("div", { class: "book-info" });
    const toolbar = h("div", { class: "actions book-actions" });
    const reserveBox = h("div", { class: "reserve-box" });
    const editor = h("div", { class: "copy-editor" });
    const parts = h("div", { class: "book-parts" });
    let book = null;

    async function load() {
      book = await get(`/books/${id}`);
      replace(
        info,
        section(
          "Book data",
          definitionList([
            ["Title", book.title],
            ["Subtitle", fmtText(book.subtitle)],
            ["Authors", authorNames(book)],
            ["Publisher", book.publisher.name],
            ["Year", String(book.publication_year)],
            ["ISBN", book.isbn],
            ["Language", book.language],
            ["Classification", book.classification],
          ]),
        ),
        section(
          "Availability",
          table({
            columns: [
              { label: "Branch", value: (a) => branchName(map, a.branch_id) },
              { label: "Available", value: (a) => String(a.available) },
              { label: "Total", value: (a) => String(a.total) },
            ],
            rows: book.availability,
          }),
        ),
      );
    }

    const copies = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Barcode", value: (c) => c.barcode },
        { label: "Status", value: (c) => words(c.status) },
        { label: "Current branch", value: (c) => branchName(map, c.current_branch_id) },
        { label: "Home branch", value: (c) => branchName(map, c.home_branch_id) },
        { label: "Shelf", value: (c) => fmtText(c.shelf_location) },
        ...(ctx.isStaff
          ? [
              { label: "Price", value: (c) => fmtAmount(c.price) },
              { label: "Acquired", value: (c) => fmtDate(c.acquired_on) },
              {
                label: "Actions",
                value: (c) =>
                  h(
                    "span",
                    { class: "row-actions" },
                    button("Change", () => openCopyEditor(c)),
                    button("Withdraw", () => askWithdraw(c)),
                    button("Repaired", () =>
                      ctx.act(() => post(`/copies/${c.id}/repair`), `Copy ${c.barcode} repaired.`, reloadAll),
                    ),
                  ),
              },
            ]
          : []),
      ],
      load: (page) => get(`/books/${id}/copies`, { page, page_size: 20 }),
    });
    const reloadAll = () => Promise.all([load(), copies.reload()]);

    function askWithdraw(copy) {
      const reason = field({ name: "reason", label: "Reason", type: "textarea", hint: "5–500 characters." });
      ctx.ask({
        text: `Withdraw copy ${copy.barcode} from the collection? This is final.`,
        extra: reason,
        onConfirm: () =>
          ctx.act(() => post(`/copies/${copy.id}/withdraw`, { reason: reason.input.value.trim() }), `Copy ${copy.barcode} withdrawn.`, reloadAll),
      });
    }

    function openCopyEditor(copy) {
      const price = field({ name: "price", label: "Price", value: copy.price, inputmode: "decimal" });
      const shelf = field({ name: "shelf_location", label: "Shelf location", value: copy.shelf_location });
      const home = field({ name: "home_branch_id", label: "Home branch", options: branchOptions(branches), value: copy.home_branch_id });
      const node = form({
        fields: [price, shelf, home],
        submit: "Save",
        label: "Change copy",
        extra: button("Close", () => replace(editor)),
        async onSubmit(v) {
          node.fieldErrors({});
          const body = omitNull({
            price: v.price.trim() !== copy.price ? v.price.trim() : null,
            shelf_location: text(v.shelf_location) !== copy.shelf_location ? (text(v.shelf_location) ?? "") : null,
            home_branch_id: Number(v.home_branch_id) !== copy.home_branch_id ? Number(v.home_branch_id) : null,
          });
          if (body.shelf_location === "") body.shelf_location = null;
          await ctx.act(
            () => patch(`/copies/${copy.id}`, body),
            `Copy ${copy.barcode} saved.`,
            async () => {
              await reloadAll();
              replace(editor);
            },
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      replace(editor, section(`Change copy ${copy.barcode}`, node));
    }

    // actions by role
    if (ctx.isStaff) {
      replace(
        toolbar,
        button("Edit", () => ctx.navigate(`#/cat-03/${id}`)),
        button("Delete", () =>
          ctx.ask({
            text: "Delete this book?",
            onConfirm: async () => {
              const done = await ctx.act(() => del(`/books/${id}`), "Book deleted.");
              if (done !== undefined) {
                replace(info);
                replace(toolbar);
                replace(copiesSection);
              }
            },
          }),
        ),
      );
    }
    const copiesSection = section("Copies", copies.el);

    const addCopy = ctx.isStaff ? addCopyForm() : null;
    function addCopyForm() {
      const barcode = field({ name: "barcode", label: "Barcode", hint: "6–20 characters: A–Z, 0–9 and -." });
      const home = field({ name: "home_branch_id", label: "Home branch", options: branchOptions(branches, { activeOnly: true }) });
      const price = field({ name: "price", label: "Price", inputmode: "decimal", hint: "0.01–100000.00" });
      const acquired = field({ name: "acquired_on", label: "Acquired on", type: "date", value: ctx.today });
      const shelf = field({ name: "shelf_location", label: "Shelf location" });
      const node = form({
        fields: [barcode, home, price, acquired, shelf],
        submit: "Add copy",
        label: "Add copy",
        async onSubmit(v) {
          node.fieldErrors({});
          const created = await ctx.act(
            () =>
              post(`/books/${id}/copies`, {
                barcode: v.barcode.trim(),
                home_branch_id: Number(v.home_branch_id),
                price: v.price.trim(),
                acquired_on: text(v.acquired_on),
                shelf_location: text(v.shelf_location),
              }),
            (c) => `Copy ${c.barcode} added.`,
            reloadAll,
            (error) => node.fieldErrors(fieldProblems(error)),
          );
          if (created) {
            barcode.input.value = "";
            shelf.input.value = "";
          }
        },
      });
      return section("Add copy", node);
    }

    if (ctx.isMember) {
      const member = await get("/members/me");
      const pickup = field({ name: "pickup_branch_id", label: "Pickup branch", options: branchOptions(branches, { activeOnly: true }), value: member.home_branch_id });
      const node = form({
        fields: [pickup],
        submit: "Reserve",
        label: "Reserve this book",
        async onSubmit(v) {
          await ctx.act(
            () => post("/reservations", { book_id: id, pickup_branch_id: Number(v.pickup_branch_id) }),
            (r) => `Reserved. Your queue position: ${r.queue_position ?? "–"}.`,
            reloadAll,
          );
        },
      });
      replace(reserveBox, section("Reserve", node));
    }

    replace(ctx.body, info, toolbar, reserveBox, copiesSection, addCopy, editor, parts);
    await load();
    await copies.goTo(1);
    for (const part of bookPageParts) {
      try {
        parts.append(await part.render(ctx, book));
      } catch (error) {
        ctx.fail(error);
      }
    }
  },
};

// ---- LIB-UI-CAT-03 ---------------------------------------------------------------

function authorPicker(ctx, initial) {
  let chosen = [...initial];
  const chosenBox = h("ol", { class: "chosen-authors", "aria-label": "Chosen authors" });
  const search = field({ name: "author_search", label: "Search authors", hint: "Choose 1–10 authors; the order is kept." });
  const results = field({ name: "author_id", label: "Found authors", options: [], attrs: { size: "4" } });
  let timer = null;

  function paint() {
    replace(
      chosenBox,
      chosen.map((a, i) =>
        h(
          "li",
          {},
          h("span", {}, a.name),
          " ",
          button("Move up", () => move(i, -1), { disabled: i === 0 }),
          button("Move down", () => move(i, 1), { disabled: i === chosen.length - 1 }),
          button("Remove", () => {
            chosen.splice(i, 1);
            paint();
          }),
        ),
      ),
    );
  }
  function move(i, delta) {
    [chosen[i], chosen[i + delta]] = [chosen[i + delta], chosen[i]];
    paint();
  }
  async function find() {
    try {
      const data = await get("/authors", { q: search.input.value.trim(), page_size: 20 });
      results.input.replaceChildren(...data.items.map((a) => h("option", { value: String(a.id) }, a.name)));
      results.input.dataset.names = JSON.stringify(Object.fromEntries(data.items.map((a) => [a.id, a.name])));
    } catch (error) {
      ctx.fail(error);
    }
  }
  search.input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(find, 250);
  });
  search.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      clearTimeout(timer);
      find();
    }
  });
  const add = () => {
    const names = JSON.parse(results.input.dataset.names || "{}");
    for (const option of results.input.selectedOptions) {
      const authorId = Number(option.value);
      if (!chosen.some((a) => a.id === authorId) && chosen.length < 10) chosen.push({ id: authorId, name: names[authorId] || option.textContent });
    }
    paint();
  };
  paint();
  find();
  const node = h(
    "div",
    { class: "author-picker" },
    chosenBox,
    search,
    results,
    h("div", { class: "actions" }, button("Search", () => find()), button("Add author", add)),
  );
  return { node, ids: () => chosen.map((a) => a.id) };
}

const bookFormScreen = {
  id: "cat-03",
  title: "Book form",
  module: "Catalog",
  roles: ["librarian", "admin"],
  async render(ctx) {
    let id = /^\d+$/.test(ctx.param) ? Number(ctx.param) : null;
    const [publishers] = await Promise.all([fetchAll("/publishers")]);
    let book = id === null ? null : await get(`/books/${id}`);
    const isbn = field({ name: "isbn", label: "ISBN", value: book?.isbn, hint: "ISBN-10 or ISBN-13; hyphens are allowed." });
    const title = field({ name: "title", label: "Title", value: book?.title });
    const subtitle = field({ name: "subtitle", label: "Subtitle", value: book?.subtitle });
    const picker = authorPicker(ctx, book ? book.authors : []);
    const publisher = field({ name: "publisher_id", label: "Publisher", options: recordOptions(publishers, (p) => p.name), value: book?.publisher.id });
    const year = field({ name: "publication_year", label: "Publication year", type: "number", value: book?.publication_year });
    const language = field({ name: "language", label: "Language", value: book?.language, hint: "Two lower-case letters, for example tr." });
    const classification = field({ name: "classification", label: "Classification", value: book?.classification, hint: "Three digits, optionally a dot and 1–6 digits, for example 005.133." });
    const links = h("p", { class: "form-links" });
    const node = form({
      fields: [isbn, title, subtitle, picker.node, publisher, year, language, classification],
      submit: "Save",
      label: "Book form",
      async onSubmit(v) {
        node.fieldErrors({});
        const subtitleValue = text(v.subtitle);
        const full = {
          isbn: v.isbn.trim(),
          title: v.title.trim(),
          subtitle: subtitleValue,
          author_ids: picker.ids(),
          publisher_id: int(v.publisher_id),
          publication_year: int(v.publication_year),
          language: v.language.trim(),
          classification: v.classification.trim(),
        };
        let request;
        if (id === null) {
          request = () => post("/books", full);
        } else {
          const body = {};
          if (full.isbn !== book.isbn) body.isbn = full.isbn;
          if (full.title !== book.title) body.title = full.title;
          if (full.subtitle !== book.subtitle) body.subtitle = full.subtitle;
          if (JSON.stringify(full.author_ids) !== JSON.stringify(book.authors.map((a) => a.id))) body.author_ids = full.author_ids;
          if (full.publisher_id !== book.publisher.id) body.publisher_id = full.publisher_id;
          if (full.publication_year !== book.publication_year) body.publication_year = full.publication_year;
          if (full.language !== book.language) body.language = full.language;
          if (full.classification !== book.classification) body.classification = full.classification;
          request = () => patch(`/books/${id}`, body);
        }
        const saved = await ctx.act(
          request,
          "Book saved.",
          null,
          (error) => node.fieldErrors(fieldProblems(error)),
        );
        if (saved) {
          book = saved;
          id = saved.id;
          history.replaceState(null, "", `#/cat-03/${id}`);
          isbn.input.value = saved.isbn;
          replace(links, link("Open book page", `#/cat-02/${id}`));
        }
      },
    });
    if (book) replace(links, link("Open book page", `#/cat-02/${book.id}`));
    replace(ctx.body, node, links);
  },
};

// ---- LIB-UI-CAT-04 ---------------------------------------------------------------

function namesSection(ctx, { title, path, singular }) {
  const q = field({ name: "q", label: `Search ${title.toLowerCase()}` });
  const editor = h("div", { class: "name-editor" });
  const list = pagedTable({
    onError: (e) => ctx.fail(e),
    columns: [
      { label: "ID", value: (r) => String(r.id) },
      { label: "Name", value: (r) => r.name },
      {
        label: "Actions",
        value: (r) =>
          h(
            "span",
            { class: "row-actions" },
            button("Rename", () => openRename(r)),
            button("Delete", () =>
              ctx.ask({
                text: `Delete ${singular} “${r.name}”?`,
                onConfirm: () => ctx.act(() => del(`${path}/${r.id}`), `${singular[0].toUpperCase()}${singular.slice(1)} deleted.`, () => list.reload()),
              }),
            ),
          ),
      },
    ],
    load: (page) => get(path, { page, page_size: 20, q: q.input.value.trim() }),
  });
  const filters = form({
    fields: [q],
    submit: "Search",
    label: `Search ${title.toLowerCase()}`,
    onSubmit() {
      ctx.clearMessages();
      list.goTo(1);
    },
  });
  const name = field({ name: "name", label: `${singular[0].toUpperCase()}${singular.slice(1)} name` });
  const create = form({
    fields: [name],
    submit: "Create",
    label: `Create ${singular}`,
    async onSubmit(v) {
      const done = await ctx.act(() => post(path, { name: v.name.trim() }), `${singular[0].toUpperCase()}${singular.slice(1)} created.`, () => list.reload());
      if (done) name.input.value = "";
    },
  });
  function openRename(record) {
    const input = field({ name: "name", label: `New name of “${record.name}”`, value: record.name });
    const node = form({
      fields: [input],
      submit: "Save",
      label: `Rename ${singular}`,
      extra: button("Close", () => replace(editor)),
      async onSubmit(v) {
        await ctx.act(() => patch(`${path}/${record.id}`, { name: v.name.trim() }), `${singular[0].toUpperCase()}${singular.slice(1)} renamed.`, async () => {
          await list.reload();
          replace(editor);
        });
      },
    });
    replace(editor, node);
  }
  const el = section(title, create, filters, list.el, editor);
  return { el, load: () => list.goTo(1) };
}

const authorsScreen = {
  id: "cat-04",
  title: "Authors and publishers",
  module: "Catalog",
  roles: ["librarian", "admin"],
  async render(ctx) {
    const authors = namesSection(ctx, { title: "Authors", path: "/authors", singular: "author" });
    const publishers = namesSection(ctx, { title: "Publishers", path: "/publishers", singular: "publisher" });
    replace(ctx.body, authors.el, publishers.el);
    await Promise.all([authors.load(), publishers.load()]);
  },
};

export const catalogScreens = [booksScreen, bookPageScreen, bookFormScreen, authorsScreen];
