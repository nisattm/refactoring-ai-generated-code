// Small DOM helpers shared by all screens: elements, form fields, tables, paging, formatting.

import { NETWORK_MESSAGE } from "./api.js";

// ---- elements --------------------------------------------------------------------

export function h(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (key === "value") node.value = value;
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, value);
  }
  append(node, children);
  return node;
}

function append(node, children) {
  for (const child of children.flat(Infinity)) {
    if (child === undefined || child === null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function clear(node) {
  node.replaceChildren();
  return node;
}

export function replace(node, ...children) {
  node.replaceChildren();
  append(node, children);
  return node;
}

// ---- formatting (LIB-UI-GEN-14) --------------------------------------------------

export const dash = "–";
export const fmtDate = (value) => (value ? String(value).slice(0, 10) : dash);
export const fmtTime = (value) => (value ? String(value).slice(11, 16) : dash);
export const fmtDateTime = (value) => (value ? `${fmtDate(value)} ${fmtTime(value)}` : dash);
export const fmtAmount = (value) => (value === null || value === undefined || value === "" ? dash : `${value} TL`);
export const fmtBool = (value) => (value ? "Yes" : "No");
export const fmtText = (value) => (value === null || value === undefined || value === "" ? dash : String(value));

export function words(code) {
  return String(code).replaceAll("_", " ");
}

// ---- errors escaping from handlers ---------------------------------------------------

let reporter = (error) => console.error(error);
export const setErrorReporter = (fn) => {
  reporter = fn;
};

/** Runs a handler; anything it throws is shown on the screen instead of being left uncaught. */
export function guarded(handler) {
  return (...args) => {
    try {
      const result = handler(...args);
      if (result && typeof result.catch === "function") result.catch((error) => reporter(error));
    } catch (error) {
      reporter(error);
    }
  };
}

// ---- ids -------------------------------------------------------------------------

let counter = 0;
export const uid = (prefix = "f") => `${prefix}-${(counter += 1)}`;

// ---- form fields (LIB-UI-GEN-10) -------------------------------------------------

/**
 * One labelled form control.
 * spec: {name, label, type, options, value, hint, placeholder, rows, readonly, attrs}
 * options: [{value, label}] makes a select.
 */
export function field(spec) {
  const id = spec.id || uid(spec.name || "field");
  const wrap = h("div", { class: "field" });
  const label = h("label", { for: id }, spec.label);
  let input;
  if (spec.options) {
    input = h("select", { id, name: spec.name });
    for (const option of spec.options) {
      input.append(h("option", { value: String(option.value) }, option.label));
    }
    if (spec.value !== undefined && spec.value !== null) input.value = String(spec.value);
  } else if (spec.type === "textarea") {
    input = h("textarea", { id, name: spec.name, rows: spec.rows || 3 });
    input.value = spec.value ?? "";
  } else {
    input = h("input", {
      id,
      name: spec.name,
      type: spec.type || "text",
      placeholder: spec.placeholder,
      inputmode: spec.inputmode,
      min: spec.min,
      max: spec.max,
      step: spec.step,
      accept: spec.accept,
      autocomplete: spec.autocomplete,
    });
    if (spec.type !== "file") input.value = spec.value ?? "";
  }
  if (spec.readonly) input.setAttribute("readonly", "");
  if (spec.required) input.setAttribute("aria-required", "true");
  for (const [key, value] of Object.entries(spec.attrs || {})) input.setAttribute(key, value);
  wrap.append(label, input);
  let describedBy = [];
  if (spec.hint) {
    const hintId = `${id}-hint`;
    wrap.append(h("small", { class: "hint", id: hintId }, spec.hint));
    describedBy.push(hintId);
  }
  const errorBox = h("small", { class: "field-error", id: `${id}-error` });
  wrap.append(errorBox);
  describedBy.push(errorBox.id);
  input.setAttribute("aria-describedby", describedBy.join(" "));
  wrap.input = input;
  wrap.setError = (text) => {
    errorBox.textContent = text || "";
    if (text) input.setAttribute("aria-invalid", "true");
    else input.removeAttribute("aria-invalid");
  };
  return wrap;
}

export const anyOption = (label = "Any") => ({ value: "", label });

export function choices(values, { any, labels = {} } = {}) {
  const list = values.map((value) => ({ value, label: labels[value] || words(value) }));
  return any === undefined ? list : [anyOption(any), ...list];
}

export const BOOLEAN_FILTER = [anyOption(), { value: "true", label: "Yes" }, { value: "false", label: "No" }];

export function branchOptions(branches, { any, activeOnly = false } = {}) {
  const list = branches
    .filter((b) => !activeOnly || b.is_active)
    .map((b) => ({ value: b.id, label: `${b.code} – ${b.name}` }));
  return any === undefined ? list : [anyOption(any), ...list];
}

export function recordOptions(records, labelOf, { any } = {}) {
  const list = records.map((r) => ({ value: r.id, label: labelOf(r) }));
  return any === undefined ? list : [anyOption(any), ...list];
}

/** Collects the values of the named controls of a container as strings. */
export function values(container) {
  const out = {};
  for (const input of container.querySelectorAll("input[name], select[name], textarea[name]")) {
    if (input.type === "file") continue;
    if (input.type === "checkbox") out[input.name] = input.checked;
    else out[input.name] = input.value;
  }
  return out;
}

/** A form with fields and one submit button; onSubmit gets the raw string values. */
export function form({ fields, submit, onSubmit, label, extra, cls }) {
  const node = h("form", { class: cls ? `form ${cls}` : "form", novalidate: true, "data-form": label });
  for (const f of fields) node.append(f);
  const actions = h("div", { class: "actions" });
  if (submit) actions.append(h("button", { type: "submit" }, submit));
  if (extra) append(actions, [extra]);
  node.append(actions);
  node.addEventListener("submit", (event) => {
    event.preventDefault();
    guarded(onSubmit)(values(node), node);
  });
  node.fieldErrors = (problems) => {
    for (const f of fields) f.setError?.("");
    for (const [name, text] of Object.entries(problems || {})) {
      const target = fields.find((f) => f.input && f.input.name === name);
      if (target) target.setError(text);
    }
  };
  return node;
}

// ---- value conversion for request bodies ----------------------------------------

/** "" → null; otherwise the trimmed text. */
export const text = (value) => {
  const trimmed = String(value ?? "").trim();
  return trimmed === "" ? null : trimmed;
};

/** "" → null; numbers → number; anything else is sent unchanged so the API rejects it. */
export const int = (value) => {
  const trimmed = String(value ?? "").trim();
  if (trimmed === "") return null;
  return /^-?\d+$/.test(trimmed) ? Number(trimmed) : trimmed;
};

export function omitNull(object) {
  return Object.fromEntries(Object.entries(object).filter(([, value]) => value !== null && value !== undefined));
}

// ---- errors (LIB-UI-GEN-12) ------------------------------------------------------

export function detailLines(details) {
  const lines = [];
  for (const [key, value] of Object.entries(details || {})) {
    if (key === "fields" && Array.isArray(value)) {
      for (const item of value) lines.push(`${item.field}: ${item.problem}`);
    } else if (Array.isArray(value)) {
      lines.push(`${key}: ${value.map((x) => (typeof x === "object" ? JSON.stringify(x) : x)).join(", ")}`);
    } else if (value !== null && typeof value === "object") {
      lines.push(`${key}: ${JSON.stringify(value)}`);
    } else {
      lines.push(`${key}: ${value}`);
    }
  }
  return lines;
}

export function alertContent(error) {
  if (!error || error.code === "NETWORK_ERROR") return [NETWORK_MESSAGE];
  const parts = [h("p", {}, h("strong", { class: "error-code" }, error.code), ": ", error.message)];
  const lines = detailLines(error.details);
  if (lines.length) parts.push(h("ul", { class: "error-details" }, lines.map((line) => h("li", {}, line))));
  return parts;
}

/** field name → problem text, from a 422 answer. */
export function fieldProblems(error) {
  const out = {};
  const list = error?.details?.fields;
  if (Array.isArray(list)) for (const item of list) out[item.field] = item.problem;
  return out;
}

// ---- tables and lists (LIB-UI-GEN-13) -------------------------------------------

/**
 * columns: [{label, value: row => text|Node}]; the table always has a header row.
 * An empty list shows "No records".
 */
export function table({ columns, rows, caption, rowClass, onRowClick }) {
  const head = h("tr", {}, columns.map((c) => h("th", { scope: "col" }, c.label)));
  const body = h("tbody");
  if (!rows.length) {
    body.append(h("tr", {}, h("td", { colspan: columns.length }, "No records")));
  }
  for (const row of rows) {
    const tr = h("tr", { class: rowClass ? rowClass(row) : undefined });
    if (onRowClick) {
      tr.classList.add("clickable");
      tr.addEventListener("click", (event) => {
        if (!event.target.closest("a, button, input, select, textarea")) onRowClick(row);
      });
    }
    for (const c of columns) {
      const content = c.value(row);
      tr.append(h("td", { "data-label": c.label }, content === undefined ? dash : content));
    }
    body.append(tr);
  }
  const t = h("table", {}, caption ? h("caption", {}, caption) : null, h("thead", {}, head), body);
  return h("div", { class: "table-wrap" }, t);
}

export function pager({ page, pageSize, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return h(
    "nav",
    { class: "pager", "aria-label": "Pagination" },
    h("button", { type: "button", disabled: page <= 1, onclick: () => onPage(page - 1) }, "Previous"),
    h("span", { class: "page-info" }, `Page ${page} of ${pages} (${total})`),
    h("button", { type: "button", disabled: page >= pages, onclick: () => onPage(page + 1) }, "Next"),
  );
}

/**
 * A paginated table. load(page) → {items, page, page_size, total}.
 * Returns {el, reload, goTo}; filters are read through getQuery by the loader.
 */
export function pagedTable({ columns, load, rowClass, onError, caption, extraAbove, onRowClick }) {
  const el = h("div", { class: "paged" });
  let page = 1;
  let ticket = 0;
  async function show(target) {
    const mine = (ticket += 1);
    try {
      const data = await load(target);
      if (mine !== ticket) return;
      page = data.page;
      // a page beyond the last one (after deleting rows) goes back one page
      if (!data.items.length && data.page > 1 && data.total > 0) return show(Math.max(1, Math.ceil(data.total / data.page_size)));
      replace(
        el,
        extraAbove ? extraAbove(data) : null,
        table({ columns, rows: data.items, rowClass, caption, onRowClick }),
        pager({ page: data.page, pageSize: data.page_size, total: data.total, onPage: show }),
      );
    } catch (error) {
      if (mine === ticket) onError?.(error);
    }
  }
  return { el, reload: () => show(page), goTo: (n = 1) => show(n) };
}

export function button(textContent, onclick, attrs = {}) {
  return h("button", { type: "button", onclick: guarded(onclick), ...attrs }, textContent);
}

export function section(title, ...children) {
  const heading = h("h2", {}, title);
  return h("section", { class: "panel", "data-section": title }, heading, ...children);
}

export function definitionList(pairs) {
  const dl = h("dl", { class: "facts" });
  for (const [term, value] of pairs) dl.append(h("dt", {}, term), h("dd", {}, value ?? dash));
  return dl;
}

export function link(textContent, href, attrs = {}) {
  return h("a", { href, ...attrs }, textContent);
}
