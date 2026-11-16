// The context object handed to every screen: user, today, messages, confirmation, shared lookups.

import { ApiError, clientError, fetchAll, get } from "./api.js";
import { alertContent, button, clear, h, replace } from "./ui.js";

function cached(cache, id, load) {
  if (!cache.has(id)) {
    const promise = load();
    cache.set(id, promise);
    promise.catch(() => cache.delete(id));
  }
  return cache.get(id);
}

export function createContext({ user, today, main, param, refreshHeader }) {
  const messages = h("div", { class: "messages" });
  const confirmation = h("div", { class: "confirmation" });
  const body = h("div", { class: "screen-body" });
  let branchCache = null;
  const copyCache = new Map();
  const bookCache = new Map();
  const memberCache = new Map();

  const ctx = {
    user,
    role: user.role,
    isStaff: user.role === "librarian" || user.role === "admin",
    isAdmin: user.role === "admin",
    isMember: user.role === "member",
    today,
    param,
    body,
    messages,
    confirmation,

    clearMessages() {
      clear(messages);
    },
    clearConfirmation() {
      clear(confirmation);
    },
    ok(text) {
      replace(messages, h("p", { role: "status", class: "status" }, text));
    },
    fail(error) {
      const shown = error instanceof ApiError ? error : clientError("CLIENT_ERROR", String(error?.message || error));
      replace(messages, h("div", { role: "alert", class: "alert" }, alertContent(shown)));
      messages.scrollIntoView?.({ block: "nearest" });
    },

    /**
     * Runs an action: clears the old message, shows the success text and reloads the data,
     * or shows the error. Returns the result, or undefined after an error.
     */
    async act(run, successText, after, onError) {
      ctx.clearMessages();
      let result;
      try {
        result = await run();
      } catch (error) {
        ctx.fail(error);
        onError?.(error);
        return undefined;
      }
      const text = typeof successText === "function" ? successText(result) : successText;
      if (text) ctx.ok(text);
      ctx.clearConfirmation();
      try {
        await after?.(result);
      } catch (error) {
        ctx.fail(error);
      }
      refreshHeader?.();
      return result === undefined ? null : result;
    },

    /** Inline confirmation (LIB-UI-GEN-15): buttons "Confirm" and "Back". */
    ask({ text, extra, onConfirm }) {
      ctx.clearMessages();
      const panel = h(
        "div",
        { class: "confirm", role: "group", "aria-label": "Confirmation" },
        h("p", {}, text),
        extra || null,
        h(
          "div",
          { class: "actions" },
          button("Confirm", () => onConfirm()),
          button("Back", () => ctx.clearConfirmation()),
        ),
      );
      replace(confirmation, panel);
      panel.querySelector("button")?.focus();
    },

    navigate(hash) {
      if (location.hash === hash) window.dispatchEvent(new HashChangeEvent("hashchange"));
      else location.hash = hash;
    },

    async branches() {
      if (!branchCache) branchCache = fetchAll("/branches");
      try {
        return await branchCache;
      } catch (error) {
        branchCache = null;
        throw error;
      }
    },
    forgetBranches() {
      branchCache = null;
    },

    // Copies and books are looked up once per screen (barcode, title and ISBN do not change meanwhile).
    copy: (id) => cached(copyCache, id, () => get(`/copies/${id}`)),
    book: (id) => cached(bookCache, id, () => get(`/books/${id}`)),
    member: (id) => cached(memberCache, id, () => get(`/members/${id}`)),

    mount() {
      replace(main, ctx.h1 || null, messages, confirmation, body);
    },
  };
  return ctx;
}

// ---- lookups by business key (LIB-UI-GEN-10) -------------------------------------

/** Member by `member_no`: the filter `q` of LIB-MEM-06, exact match on the member number. */
export async function findMember(memberNo) {
  const wanted = String(memberNo ?? "").trim();
  if (!wanted) throw clientError("VALIDATION_ERROR", "Enter a member number.", { fields: [{ field: "member_no", problem: "field required" }] });
  const data = await get("/members", { q: wanted, page_size: 100 });
  const found = data.items.find((m) => m.member_no.toLowerCase() === wanted.toLowerCase());
  if (!found) throw clientError("NOT_FOUND", `No member with member number ${wanted}.`, { field: "member_no", value: wanted });
  return found;
}

/** Book by `isbn` (LIB-CAT-04 filter, exact after normalization). */
export async function findBook(isbn) {
  const wanted = String(isbn ?? "").trim();
  if (!wanted) throw clientError("VALIDATION_ERROR", "Enter an ISBN.", { fields: [{ field: "isbn", problem: "field required" }] });
  const data = await get("/books", { isbn: wanted, page_size: 1 });
  if (!data.items.length) throw clientError("NOT_FOUND", `No book with ISBN ${wanted}.`, { field: "isbn", value: wanted });
  return data.items[0];
}

export const bookLabel = (book) => `${book.title} (${book.isbn})`;
