// Module 26: reading programs (management, join, my progress, leaderboard, manual entries, report).

import { api, clientError, del, fetchAll, get, patch, post } from "../api.js";
import { findBook, findMember } from "../context.js";
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
  fmtDateTime,
  fmtText,
  form,
  h,
  int,
  link,
  omitNull,
  pagedTable,
  replace,
  section,
  table,
  text,
  uid,
  words,
} from "../ui.js";
import { branchMap, branchName } from "../views.js";

const AUDIENCES = ["all", "students", "academics"];
const PROGRAM_STATUSES = ["draft", "published", "closed", "cancelled"];
const PARTICIPATION_STATUSES = ["active", "left", "completed"];
const SOURCES = ["loan", "manual", "event", "bonus"];
const MANUAL_LIMIT = 3;

const put = (path, body) => api("PUT", path, { body });

// ---- helpers ---------------------------------------------------------------------

const programLabel = (p) => `${p.name} (${fmtDate(p.starts_on)} – ${fmtDate(p.ends_on)}, ${p.status})`;
const freePlaces = (p) => (p.free_places === null || p.free_places === undefined ? "No limit" : String(p.free_places));
const limitText = (p) => (p.max_participants === null || p.max_participants === undefined ? "No limit" : String(p.max_participants));
const levelText = (level) => (level === "none" ? "none" : level);
const rankText = (rank) => (rank === null || rank === undefined ? "Not ranked" : String(rank));
const completionRate = (p) => (p.participants > 0 ? `${((p.completed / p.participants) * 100).toFixed(1)} %` : "0.0 %");

function programOptions(programs, { placeholder = "Choose a program" } = {}) {
  return [{ value: "", label: placeholder }, ...programs.map((p) => ({ value: p.id, label: programLabel(p) }))];
}

async function myMemberId() {
  return (await get("/members/me")).id;
}

/** A list that is read completely and shown in pages of `pageSize` (for lists the API cannot filter as needed). */
function clientPaged(loadAll, pageSize = 10) {
  return async (page) => {
    const all = await loadAll();
    const pages = Math.max(1, Math.ceil(all.length / pageSize));
    const current = Math.min(Math.max(1, page), pages);
    return { items: all.slice((current - 1) * pageSize, current * pageSize), page: current, page_size: pageSize, total: all.length };
  };
}

/** Entries of one participation (LIB-RDP-22); `actions(entry)` adds a column of buttons. */
function entriesList(ctx, participationId, { actions, onError } = {}) {
  const source = field({ name: "source", label: "Source", options: choices(SOURCES, { any: "Any" }) });
  const columns = [
    { label: "Date", value: (e) => fmtDate(e.on) },
    { label: "Source", value: (e) => words(e.source) },
    { label: "Book or event", value: (e) => (e.book_title ? e.book_title : e.event_id ? `Event ${e.event_id}` : "–") },
    { label: "Points", value: (e) => String(e.points) },
    { label: "Note", value: (e) => fmtText(e.note) },
  ];
  if (actions) columns.push({ label: "Actions", value: (e) => actions(e) });
  const list = pagedTable({
    onError: onError || ((e) => ctx.fail(e)),
    columns,
    load: (page) => get(`/participations/${participationId}/entries`, { page, page_size: 10, source: source.input.value }),
  });
  const filter = form({
    fields: [source],
    submit: "Filter",
    label: "Entry filters",
    cls: "filters",
    onSubmit() {
      ctx.clearMessages();
      return list.goTo(1);
    },
  });
  return { el: h("div", { class: "entries" }, filter, list.el), list };
}

// ---- LIB-UI-RDP-01 ---------------------------------------------------------------

function programFormFields({ branches, program, mode }) {
  const f = {};
  const published = mode === "published";
  if (!published) {
    f.name = field({ name: "name", label: "Name", value: program?.name, hint: "1–200 characters; unique among programs that are not cancelled." });
  }
  f.description = field({ name: "description", label: "Description", type: "textarea", value: program?.description ?? "", hint: "Up to 1000 characters." });
  if (!published) {
    f.branch_id = field({
      name: "branch_id",
      label: "Branch",
      options: [{ value: "", label: "All branches" }, ...branchOptions(branches, { activeOnly: true })],
      value: program?.branch_id ?? "",
    });
    f.audience = field({ name: "audience", label: "Audience", options: choices(AUDIENCES), value: program?.audience ?? "all" });
    f.starts_on = field({ name: "starts_on", label: "Starts on", type: "date", value: program ? fmtDate(program.starts_on) : "" });
  }
  f.ends_on = field({
    name: "ends_on",
    label: "Ends on",
    type: "date",
    value: program ? fmtDate(program.ends_on) : "",
    hint: "13 to 120 days after the start.",
  });
  if (!published) {
    f.goal_books = field({ name: "goal_books", label: "Goal (books)", type: "number", min: 1, max: 50, value: program?.goal_books ?? "" });
  }
  f.max_participants = field({
    name: "max_participants",
    label: "Maximum participants",
    type: "number",
    min: 1,
    max: 1000,
    value: program?.max_participants ?? "",
    hint: "Leave empty for no limit.",
  });
  if (!published) {
    f.reward_waiver = field({
      name: "reward_waiver",
      label: "Reward waiver",
      inputmode: "decimal",
      value: program?.reward_waiver ?? "0.00",
      hint: "Late fees waived at completion, 0.00 to 50.00 TL.",
    });
  }
  return f;
}

const programManagementScreen = {
  id: "rdp-01",
  title: "Programs",
  module: "Reading programs",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const map = await branchMap(ctx);
    const formBox = h("div", { class: "program-form" });
    const panelBox = h("div", { class: "program-panel" });

    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const status = field({ name: "status", label: "Status", options: choices(PROGRAM_STATUSES, { any: "Any" }) });
    const running = field({
      name: "running",
      label: "Running today",
      options: [
        { value: "", label: "Any" },
        { value: "true", label: "Yes" },
        { value: "false", label: "No" },
      ],
    });

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "ID", value: (p) => String(p.id) },
        { label: "Name", value: (p) => p.name },
        { label: "Status", value: (p) => p.status },
        { label: "Starts on", value: (p) => fmtDate(p.starts_on) },
        { label: "Ends on", value: (p) => fmtDate(p.ends_on) },
        { label: "Branch", value: (p) => (p.branch_id === null ? "All branches" : branchName(map, p.branch_id)) },
        { label: "Audience", value: (p) => p.audience },
        { label: "Goal", value: (p) => `${p.goal_books} books` },
        { label: "Participants", value: (p) => `${p.participants} of ${limitText(p)}` },
        { label: "Completed", value: (p) => `${p.completed} (${completionRate(p)})` },
        { label: "Free places", value: (p) => freePlaces(p) },
        { label: "Reward waiver", value: (p) => fmtAmount(p.reward_waiver) },
        {
          label: "Actions",
          value: (p) =>
            h(
              "span",
              { class: "row-actions" },
              p.status === "draft" || p.status === "published" ? button("Edit", () => openForm(p)) : null,
              p.status === "draft" ? button("Publish", () => publish(p)) : null,
              p.status === "draft" || p.status === "published" ? button("Cancel", () => cancelProgram(p)) : null,
              button("Copy", () => openCopy(p)),
              button("Participants", () => openParticipants(p)),
              button("Featured books", () => openBooks(p)),
            ),
        },
      ],
      load: (page) =>
        get("/programs", {
          page,
          page_size: 20,
          status: status.input.value,
          branch_id: branch.input.value,
          running: running.input.value,
        }),
    });
    const reload = () => list.reload();

    function publish(p) {
      return ctx.act(() => post(`/programs/${p.id}/publish`), (r) => `Program "${r.name}" published.`, reload);
    }

    function cancelProgram(p) {
      ctx.ask({
        text: `Cancel "${p.name}"? Active participants leave the program and are notified; completed participations and rewards already given stay.`,
        onConfirm: () =>
          ctx.act(() => post(`/programs/${p.id}/cancel`), `Program "${p.name}" cancelled.`, async () => {
            replace(formBox);
            replace(panelBox);
            await reload();
          }),
      });
    }

    // ---- create and change
    function openForm(program = null) {
      ctx.clearMessages();
      replace(panelBox);
      const mode = !program ? "create" : program.status === "draft" ? "draft" : "published";
      const f = programFormFields({ branches, program, mode });
      const node = form({
        fields: Object.values(f),
        submit: program ? "Save" : "Create",
        label: program ? "Change program" : "New program",
        extra: button("Close", () => replace(formBox)),
        async onSubmit(v) {
          node.fieldErrors({});
          const onError = (error) => {
            const problems = fieldProblems(error);
            if (error?.details?.field && !problems[error.details.field]) problems[error.details.field] = error.message;
            node.fieldErrors(problems);
          };
          const after = async () => {
            replace(formBox);
            await reload();
          };
          if (!program) {
            const body = omitNull({
              name: v.name.trim(),
              description: v.description.trim(),
              audience: v.audience,
              starts_on: text(v.starts_on),
              ends_on: text(v.ends_on),
              goal_books: int(v.goal_books),
              reward_waiver: text(v.reward_waiver),
            });
            body.branch_id = v.branch_id === "" ? null : Number(v.branch_id);
            body.max_participants = int(v.max_participants);
            await ctx.act(() => post("/programs", body), (r) => `Program ${r.id} created as draft.`, after, onError);
            return;
          }
          const body = {};
          if (v.description.trim() !== program.description) body.description = v.description.trim();
          if (v.ends_on !== fmtDate(program.ends_on)) body.ends_on = v.ends_on;
          if (String(int(v.max_participants) ?? "") !== String(program.max_participants ?? "")) body.max_participants = int(v.max_participants);
          if (mode === "draft") {
            if (v.name.trim() !== program.name) body.name = v.name.trim();
            if (v.branch_id !== String(program.branch_id ?? "")) body.branch_id = v.branch_id === "" ? null : Number(v.branch_id);
            if (v.audience !== program.audience) body.audience = v.audience;
            if (v.starts_on !== fmtDate(program.starts_on)) body.starts_on = v.starts_on;
            if (String(int(v.goal_books)) !== String(program.goal_books)) body.goal_books = int(v.goal_books);
            const waiver = text(v.reward_waiver);
            if (waiver !== null && Number(waiver) !== Number(program.reward_waiver)) body.reward_waiver = waiver;
          }
          await ctx.act(() => patch(`/programs/${program.id}`, body), `Program ${program.id} saved.`, after, onError);
        },
      });
      const heading = program ? `Change program ${program.id}: ${program.name}` : "New program";
      const fixed =
        mode === "published"
          ? definitionList([
              ["Name", program.name],
              ["Branch", program.branch_id === null ? "All branches" : branchName(map, program.branch_id)],
              ["Audience", program.audience],
              ["Starts on", fmtDate(program.starts_on)],
              ["Goal", `${program.goal_books} books`],
              ["Reward waiver", fmtAmount(program.reward_waiver)],
              ["Participants", String(program.participants)],
            ])
          : null;
      replace(
        formBox,
        section(heading, mode === "published" ? h("p", { class: "hint" }, "A published program allows only the description, the end date and the maximum participants to change.") : null, fixed, node),
      );
      (f.name || f.description).input.focus();
    }

    // ---- copy
    function openCopy(program) {
      ctx.clearMessages();
      replace(formBox);
      const starts = field({ name: "starts_on", label: "Starts on (new program)", type: "date", value: fmtDate(program.ends_on) });
      const node = form({
        fields: [starts],
        submit: "Copy",
        label: "Copy program",
        extra: button("Close", () => replace(panelBox)),
        async onSubmit(v) {
          node.fieldErrors({});
          await ctx.act(
            () => post(`/programs/${program.id}/copy`, { starts_on: v.starts_on }),
            (r) => `Program ${r.id} "${r.name}" created as draft (${fmtDate(r.starts_on)} – ${fmtDate(r.ends_on)}).`,
            async () => {
              replace(panelBox);
              await reload();
            },
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      replace(panelBox, section(`Copy of ${program.name}`, h("p", { class: "hint" }, "The copy is a draft with the same fields and featured books; the length stays the same."), node));
      starts.input.focus();
    }

    // ---- participants and completion
    function openParticipants(program) {
      ctx.clearMessages();
      replace(formBox);
      const status = field({ name: "status", label: "Participation status", options: choices(PARTICIPATION_STATUSES, { any: "Any" }) });
      const participants = pagedTable({
        onError: (e) => ctx.fail(e),
        columns: [
          { label: "Rank", value: (r) => rankText(r.rank) },
          { label: "Member", value: (r) => (r._member ? link(r._member.member_no, `#/mem-03/${r._member.id}`) : `#${r.member_id}`) },
          { label: "Name", value: (r) => r.full_name },
          { label: "Status", value: (r) => r.status },
          { label: "Points", value: (r) => String(r.points) },
          { label: "Books", value: (r) => `${r.books} of ${program.goal_books}` },
          { label: "Level", value: (r) => levelText(r.level) },
          { label: "Shown by name", value: (r) => fmtBool(r.public) },
          { label: "Reward waived", value: (r) => fmtAmount(r.reward_waived) },
          {
            label: "Actions",
            value: (r) =>
              r._member ? link("Manual entries", `#/rdp-05/${program.id}/${encodeURIComponent(r._member.member_no)}`) : "–",
          },
        ],
        load: async (page) => {
          const data = await get(`/programs/${program.id}/participants`, { page, page_size: 20, status: status.input.value });
          await Promise.all(
            data.items.map(async (r) => {
              try {
                r._member = await ctx.member(r.member_id);
              } catch {
                r._member = null;
              }
            }),
          );
          return data;
        },
      });
      const filter = form({
        fields: [status],
        submit: "Filter",
        label: "Participant filters",
        cls: "filters",
        onSubmit() {
          ctx.clearMessages();
          return participants.goTo(1);
        },
      });
      const summary = h("div", { class: "program-summary" });
      async function refreshSummary() {
        const fresh = await get(`/programs/${program.id}`);
        replace(
          summary,
          definitionList([
            ["Status", fresh.status],
            ["Goal", `${fresh.goal_books} books`],
            ["Participants (active and completed)", `${fresh.participants} of ${limitText(fresh)}`],
            ["Completed", `${fresh.completed} (${completionRate(fresh)})`],
            ["Free places", freePlaces(fresh)],
          ]),
        );
      }
      replace(panelBox, section(`Participants of ${program.name}`, summary, filter, participants.el, button("Close", () => replace(panelBox))));
      refreshSummary().catch((e) => ctx.fail(e));
      participants.goTo(1);
      panelBox.scrollIntoView?.({ block: "nearest" });
    }

    // ---- featured books (LIB-RDP-08)
    async function openBooks(program) {
      ctx.clearMessages();
      replace(formBox);
      const editable = program.status === "draft" || program.status === "published";
      let books = (await get(`/programs/${program.id}/books`)).items.map((b) => ({ id: b.book_id, title: b.title }));
      const listBox = h("div", { class: "featured-books" });
      function drawList() {
        replace(
          listBox,
          table({
            columns: [
              { label: "Title", value: (b) => b.title },
              {
                label: "Actions",
                value: (b) =>
                  editable
                    ? button("Remove", () => {
                        books = books.filter((x) => x.id !== b.id);
                        drawList();
                      })
                    : "–",
              },
            ],
            rows: books,
          }),
        );
      }
      drawList();
      let content;
      if (editable) {
        const isbn = field({ name: "isbn", label: "ISBN", hint: "Add a book by its ISBN, then save the list (0 to 30 books)." });
        const add = form({
          fields: [isbn],
          submit: "Add",
          label: "Add a featured book",
          cls: "filters",
          async onSubmit(v) {
            ctx.clearMessages();
            try {
              const book = await findBook(v.isbn);
              if (!books.some((b) => b.id === book.id)) books.push({ id: book.id, title: book.title });
              isbn.input.value = "";
              drawList();
            } catch (error) {
              ctx.fail(error);
            }
          },
        });
        content = [
          add,
          listBox,
          h(
            "div",
            { class: "actions" },
            button("Save", () =>
              ctx.act(
                () => put(`/programs/${program.id}/books`, { book_ids: books.map((b) => b.id) }),
                (r) => `Featured books saved: ${r.items.length} book(s).`,
              ),
            ),
            button("Close", () => replace(panelBox)),
          ),
        ];
      } else {
        content = [listBox, button("Close", () => replace(panelBox))];
      }
      replace(panelBox, section(`Featured books of ${program.name}`, ...content));
    }

    // ---- filters, new program, process
    const filters = form({
      fields: [branch, status, running],
      submit: "Filter",
      label: "Program filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return list.goTo(1);
      },
    });
    const processButton = button("Process", () =>
      ctx.act(
        () => post("/programs/process"),
        (r) =>
          `Processed. Closed programs: ${r.closed}. Participants completed: ${r.participants_completed}. Not completed: ${r.participants_not_completed}. Reminders: ${r.reminders}.`,
        reload,
      ),
    );
    replace(
      ctx.body,
      h("div", { class: "actions" }, button("New program", () => openForm()), processButton),
      h("p", { class: "hint" }, "Process closes the published programs that have ended and sends the reminders for programs that end in 3 days."),
      formBox,
      filters,
      list.el,
      panelBox,
    );
    await list.goTo(1);
    if (/^\d+$/.test(ctx.param)) {
      try {
        openParticipants(await get(`/programs/${ctx.param}`));
      } catch (error) {
        ctx.fail(error);
      }
    }
  },
};

// ---- LIB-UI-RDP-02 ---------------------------------------------------------------

function showNameBox(checked) {
  const id = uid("public");
  const input = h("input", { type: "checkbox", id, name: "public" });
  input.checked = checked;
  return { input, el: h("label", { class: "show-name", for: id }, input, " Show my name") };
}

const joinScreen = {
  id: "rdp-02",
  title: "Join",
  module: "Reading programs",
  roles: ["member"],
  async render(ctx) {
    const map = await branchMap(ctx);
    const books = new Map();
    const featured = (id) => {
      if (!books.has(id)) {
        books.set(
          id,
          get(`/programs/${id}/books`).then(
            (r) => r.items.map((b) => b.title),
            () => [],
          ),
        );
      }
      return books.get(id);
    };

    function leave(p) {
      ctx.ask({
        text: `Leave "${p.name}"? Your entries stay, but you are no longer on the leaderboard. You can join again later.`,
        onConfirm: () => ctx.act(() => post(`/programs/${p.id}/leave`, {}), `You left "${p.name}".`, reload),
      });
    }

    function actions(p) {
      const mine = p.my_participation;
      if (mine && (mine.status === "active" || mine.status === "completed")) {
        const box = showNameBox(mine.public);
        return h(
          "div",
          { class: "join-actions" },
          h("span", { class: "participation-status" }, mine.status === "completed" ? "Completed" : "You joined"),
          box.el,
          button("Save", () =>
            ctx.act(() => patch(`/participations/${mine.id}`, { public: box.input.checked }), "Your choice was saved.", reload),
          ),
          mine.status === "active" ? button("Leave", () => leave(p)) : null,
        );
      }
      const box = showNameBox(mine ? mine.public : true);
      return h(
        "div",
        { class: "join-actions" },
        mine ? h("span", { class: "participation-status" }, "You left") : null,
        box.el,
        button("Join", () => ctx.act(() => post(`/programs/${p.id}/join`, { public: box.input.checked }), `You joined "${p.name}".`, reload)),
      );
    }

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Name", value: (p) => p.name },
        { label: "Description", value: (p) => fmtText(p.description) },
        { label: "Branch", value: (p) => (p.branch_id === null ? "All branches" : branchName(map, p.branch_id)) },
        { label: "Audience", value: (p) => p.audience },
        { label: "Goal", value: (p) => `${p.goal_books} books` },
        { label: "Starts on", value: (p) => fmtDate(p.starts_on) },
        { label: "Ends on", value: (p) => fmtDate(p.ends_on) },
        { label: "Running", value: (p) => fmtBool(p.starts_on <= ctx.today && ctx.today <= p.ends_on) },
        { label: "Free places", value: (p) => freePlaces(p) },
        { label: "Reward waiver", value: (p) => fmtAmount(p.reward_waiver) },
        { label: "Featured books", value: (p) => (p._books.length ? h("ul", { class: "top-books" }, p._books.map((t) => h("li", {}, t))) : "–") },
        { label: "Actions", value: (p) => actions(p) },
      ],
      load: clientPaged(async () => {
        const all = await fetchAll("/programs", { status: "published" });
        const open = all.filter((p) => p.ends_on >= ctx.today);
        await Promise.all(
          open.map(async (p) => {
            p._books = await featured(p.id);
          }),
        );
        return open;
      }, 10),
    });
    const reload = () => list.reload();
    list.el.classList.add("cards");
    replace(ctx.body, h("p", { class: "hint" }, "Programs that are running or start later. Books you return during a program count automatically."), list.el);
    await list.goTo(1);
  },
};

// ---- LIB-UI-RDP-03 ---------------------------------------------------------------

const myProgressScreen = {
  id: "rdp-03",
  title: "My progress",
  module: "Reading programs",
  roles: ["member"],
  async render(ctx) {
    const memberId = await myMemberId();
    const detailBox = h("div", { class: "progress-detail" });
    const details = new Map();
    const programInfo = (id) => {
      if (!details.has(id)) {
        details.set(
          id,
          get(`/programs/${id}`).then(
            (p) => p,
            () => null,
          ),
        );
      }
      return details.get(id);
    };

    function openEntries(item) {
      ctx.clearMessages();
      const entries = entriesList(ctx, item.participation_id);
      replace(
        detailBox,
        section(
          `Entries for ${item.program_name}`,
          h("p", {}, `${item.points} points, ${item.books} of ${item.goal_books} books, level ${levelText(item.level)}.`),
          entries.el,
          button("Close", () => replace(detailBox)),
        ),
      );
      entries.list.goTo(1);
      detailBox.scrollIntoView?.({ block: "nearest" });
    }

    async function openCertificate(item) {
      ctx.clearMessages();
      const c = await get(`/participations/${item.participation_id}/certificate`);
      replace(
        detailBox,
        section(
          `Certificate for ${item.program_name}`,
          definitionList([
            ["Certificate number", c.certificate_no],
            ["Member", c.member_name],
            ["Program", c.program_name],
            ["Completed on", fmtDate(c.completed_at)],
            ["Level", levelText(c.level)],
            ["Books", String(c.books)],
            ["Points", String(c.points)],
          ]),
          button("Close", () => replace(detailBox)),
        ),
      );
    }

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Program", value: (r) => r.program_name },
        { label: "Status", value: (r) => r.status },
        { label: "Points", value: (r) => String(r.points) },
        { label: "Books", value: (r) => `${r.books} of ${r.goal_books}` },
        { label: "Level", value: (r) => levelText(r.level) },
        { label: "Rank", value: (r) => rankText(r.rank) },
        { label: "Completed on", value: (r) => (r._mine?.completed_at ? fmtDate(r._mine.completed_at) : "–") },
        { label: "Reward received", value: (r) => (r._mine ? fmtAmount(r._mine.reward_waived) : "–") },
        {
          label: "Actions",
          value: (r) =>
            h(
              "span",
              { class: "row-actions" },
              button("Entries", () => openEntries(r)),
              r.status === "completed" ? button("Certificate", () => openCertificate(r)) : null,
            ),
        },
      ],
      load: async (page) => {
        const data = await get(`/members/${memberId}/programs`, { page, page_size: 10 });
        await Promise.all(
          data.items.map(async (r) => {
            const program = await programInfo(r.program_id);
            r._mine = program?.my_participation ?? null;
          }),
        );
        return data;
      },
    });
    details.clear();
    replace(ctx.body, list.el, detailBox);
    await list.goTo(1);
  },
};

// ---- LIB-UI-RDP-04 ---------------------------------------------------------------

const leaderboardScreen = {
  id: "rdp-04",
  title: "Leaderboard",
  module: "Reading programs",
  roles: ["all"],
  async render(ctx) {
    const programs = await fetchAll("/programs");
    const program = field({ name: "program_id", label: "Program", options: programOptions(programs), value: /^\d+$/.test(ctx.param) ? ctx.param : "" });
    const info = h("div", { class: "leaderboard-info" });
    const out = h("div", { class: "leaderboard" });
    let current = null;

    const columns = [
      { label: "Rank", value: (r) => String(r.rank) },
      { label: "Name", value: (r) => r.name },
    ];
    if (ctx.isStaff) {
      columns.push({
        label: "Member",
        value: (r) => (r.member_id === undefined ? "–" : r._member ? link(r._member.member_no, `#/mem-03/${r._member.id}`) : `#${r.member_id}`),
      });
    }
    columns.push(
      { label: "Points", value: (r) => String(r.points) },
      { label: "Books", value: (r) => String(r.books) },
      { label: "Level", value: (r) => levelText(r.level) },
    );

    const list = pagedTable({
      onError: (e) => {
        replace(info);
        ctx.fail(e);
      },
      columns,
      load: async (page) => {
        const data = await get(`/programs/${current}/leaderboard`, { page, page_size: 20 });
        if (ctx.isStaff) {
          await Promise.all(
            data.items.map(async (r) => {
              if (r.member_id === undefined) return;
              try {
                r._member = await ctx.member(r.member_id);
              } catch {
                r._member = null;
              }
            }),
          );
        }
        return data;
      },
    });

    const node = form({
      fields: [program],
      submit: "Show",
      label: "Choose a program",
      cls: "filters",
      async onSubmit(v) {
        ctx.clearMessages();
        const chosen = programs.find((p) => String(p.id) === v.program_id);
        if (!chosen) {
          replace(info, h("p", { class: "hint" }, "Choose a program to see its leaderboard."));
          replace(out);
          return;
        }
        current = chosen.id;
        replace(
          info,
          definitionList([
            ["Program", chosen.name],
            ["Dates", `${fmtDate(chosen.starts_on)} – ${fmtDate(chosen.ends_on)}`],
            ["Goal", `${chosen.goal_books} books`],
            ["Status", chosen.status],
            ctx.isMember && chosen.my_participation ? ["Your rank", rankText(chosen.my_participation.rank)] : null,
          ].filter(Boolean)),
        );
        replace(out, list.el);
        await list.goTo(1);
      },
    });
    replace(ctx.body, node, info, out);
    if (program.input.value) node.requestSubmit();
  },
};

// ---- LIB-UI-RDP-05 ---------------------------------------------------------------

const manualEntriesScreen = {
  id: "rdp-05",
  title: "Manual entries",
  module: "Reading programs",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const programs = await fetchAll("/programs");
    const [paramProgram, ...rest] = ctx.param.split("/");
    const program = field({
      name: "program_id",
      label: "Program",
      options: programOptions(programs),
      value: /^\d+$/.test(paramProgram) ? paramProgram : "",
    });
    const memberNo = field({ name: "member_no", label: "Member number", value: rest.join("/"), hint: "For example M000001." });
    const out = h("div", { class: "manual-entries" });
    let shown = null;

    async function show(programId, member) {
      const participants = await fetchAll(`/programs/${programId}/participants`);
      const part = participants.find((p) => p.member_id === member.id);
      if (!part) {
        replace(out);
        throw clientError("NOT_FOUND", `Member ${member.member_no} has not joined this program.`, {
          field: "member_no",
          value: member.member_no,
        });
      }
      const programRecord = await get(`/programs/${programId}`);
      const manual = await fetchAll(`/participations/${part.participation_id}/entries`, { source: "manual" });
      const entries = entriesList(ctx, part.participation_id, {
        onError: (e) => ctx.fail(e),
        actions: (e) =>
          e.source === "manual" ? button("Remove", () => askRemove(e)) : "–",
      });

      async function refresh() {
        if (!shown) return;
        await show(shown.programId, shown.member);
      }

      function askRemove(entry) {
        ctx.ask({
          text: `Remove the manual entry "${entry.book_title ?? entry.id}" of ${member.full_name}? Points, books and level are recomputed; a completion is not taken back.`,
          onConfirm: () => ctx.act(() => del(`/program-entries/${entry.id}`), "Entry removed.", refresh),
        });
      }

      const isbn = field({ name: "isbn", label: "ISBN", hint: "The book read elsewhere." });
      const note = field({ name: "note", label: "Note", hint: "Up to 200 characters." });
      const add = form({
        fields: [isbn, note],
        submit: "Add",
        label: "Add a manual entry",
        async onSubmit(v) {
          ctx.clearMessages();
          let book;
          try {
            book = await findBook(v.isbn);
          } catch (error) {
            ctx.fail(error);
            return;
          }
          await ctx.act(
            () => post(`/participations/${part.participation_id}/entries`, { book_id: book.id, note: v.note.trim() }),
            (r) => `Entry added: "${r.book_title}", ${r.points} points.`,
            refresh,
          );
        },
      });

      replace(
        out,
        section(
          `${member.full_name} in ${programRecord.name}`,
          definitionList([
            ["Member", `${member.member_no} – ${member.full_name}`],
            ["Program", `${programRecord.name} (${programRecord.status}, ${fmtDate(programRecord.starts_on)} – ${fmtDate(programRecord.ends_on)})`],
            ["Participation", part.status],
            ["Points", String(part.points)],
            ["Books", `${part.books} of ${programRecord.goal_books}`],
            ["Level", levelText(part.level)],
            ["Manual entries", `${manual.length} of ${MANUAL_LIMIT}`],
          ]),
        ),
        section("Add a book", add),
        section("Entries", entries.el),
      );
      shown = { programId, member };
      await entries.list.goTo(1);
    }

    const node = form({
      fields: [program, memberNo],
      submit: "Show",
      label: "Choose a participant",
      cls: "filters",
      async onSubmit(v) {
        ctx.clearMessages();
        shown = null;
        replace(out);
        if (!program.input.value) {
          ctx.fail(clientError("VALIDATION_ERROR", "Choose a program.", { fields: [{ field: "program_id", problem: "field required" }] }));
          return;
        }
        const member = await findMember(v.member_no);
        await show(Number(v.program_id), member);
      },
    });
    replace(ctx.body, node, out);
    if (program.input.value && memberNo.input.value) node.requestSubmit();
  },
};

// ---- LIB-UI-RDP-06 ---------------------------------------------------------------

const programsReportScreen = {
  id: "rdp-06",
  title: "Programs report",
  module: "Reading programs",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const from = field({ name: "from", label: "From", type: "date", value: `${ctx.today.slice(0, 4)}-01-01` });
    const to = field({ name: "to", label: "To", type: "date", value: ctx.today });
    const out = h("div", { class: "report" });
    const list = pagedTable({
      onError: (e) => {
        replace(out);
        ctx.fail(e);
      },
      columns: [
        { label: "Program", value: (r) => r.name },
        { label: "Status", value: (r) => r.status },
        { label: "Participants", value: (r) => String(r.participants) },
        { label: "Completed", value: (r) => String(r.completed) },
        { label: "Completion rate", value: (r) => `${r.completion_rate} %` },
        { label: "Books counted", value: (r) => String(r.books_counted) },
        { label: "Points", value: (r) => String(r.points) },
        { label: "Rewards waived", value: (r) => fmtAmount(r.rewards_waived) },
        {
          label: "Top books",
          value: (r) =>
            r.top_books.length
              ? h("ol", { class: "top-books" }, r.top_books.map((b) => h("li", {}, `${b.title} (${b.count})`)))
              : "–",
        },
      ],
      load: (page) => get("/reports/programs", { page, page_size: 50, from: from.input.value, to: to.input.value }),
    });
    const node = form({
      fields: [from, to],
      submit: "Show",
      label: "Programs report",
      cls: "filters",
      async onSubmit() {
        ctx.clearMessages();
        replace(out, list.el);
        await list.goTo(1);
      },
    });
    replace(ctx.body, node, out);
    node.requestSubmit();
  },
};

export const programScreens = [
  programManagementScreen,
  joinScreen,
  myProgressScreen,
  leaderboardScreen,
  manualEntriesScreen,
  programsReportScreen,
];
