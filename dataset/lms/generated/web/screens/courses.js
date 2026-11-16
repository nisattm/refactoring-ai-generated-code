// Module 21: course reserves (courses, enrollment, reading list, reserve desk, my courses, report).

import { api, clientError, fetchAll, get, patch, post } from "../api.js";
import { findMember } from "../context.js";
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
  recordOptions,
  replace,
  section,
  table,
  text,
  values,
  words,
} from "../ui.js";
import { branchMap, branchName } from "../views.js";

const COURSE_STATUSES = ["draft", "active", "closed"];
const ENROLLMENT_STATUSES = ["enrolled", "dropped"];
const ITEM_KINDS = ["required", "recommended"];
const LOAN_PERIODS = [
  { value: "2h", label: "2 hours" },
  { value: "1d", label: "1 day" },
  { value: "3d", label: "3 days" },
];
const LOAN_STATUSES = ["open", "returned", "lost"];
const BOOLEAN = [
  { value: "", label: "Any" },
  { value: "true", label: "Yes" },
  { value: "false", label: "No" },
];

// ---- helpers ---------------------------------------------------------------------

function addDays(isoDate, days) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

const courseLabel = (c) => `${c.code} – ${c.title} (${c.term})`;
const periodLabel = (value) => LOAN_PERIODS.find((p) => p.value === value)?.label ?? value;

async function memberText(ctx, id) {
  try {
    const m = await ctx.member(id);
    return `${m.member_no} ${m.full_name}`;
  } catch {
    return `#${id}`;
  }
}

async function withInstructors(ctx, courses) {
  await Promise.all(
    courses.map(async (c) => {
      c._instructor = await memberText(ctx, c.instructor_id);
    }),
  );
  return courses;
}

function courseFacts(course, map, instructor) {
  return definitionList([
    ["Code", course.code],
    ["Title", course.title],
    ["Term", course.term],
    ["Branch", branchName(map, course.branch_id)],
    ["Instructor", instructor],
    ["Dates", `${fmtDate(course.starts_on)} to ${fmtDate(course.ends_on)}`],
    ["Status", course.status],
    ["Enrolled", `${course.enrolled} of ${course.enrollment_limit}`],
    ["Reading list items", String(course.items)],
    ["Copies on reserve", String(course.copies_on_reserve)],
  ]);
}

/** Field to choose a course when a screen is opened without one (LIB-UI-GEN-03). */
function coursePicker(ctx, courses, route) {
  const choose = field({
    name: "course_id",
    label: "Course",
    options: courses.length ? recordOptions(courses, courseLabel) : [{ value: "", label: "No courses" }],
  });
  return form({
    fields: [choose],
    submit: "Open",
    label: "Choose a course",
    onSubmit(v) {
      if (v.course_id) ctx.navigate(`#/${route}/${v.course_id}`);
    },
  });
}

function courseIdFromParam(ctx) {
  return /^\d+$/.test(ctx.param) ? Number(ctx.param) : null;
}

async function reserveLoanRows(ctx, items) {
  await Promise.all(
    items.map(async (l) => {
      try {
        l._copy = await ctx.copy(l.copy_id);
      } catch {
        l._copy = null;
      }
      try {
        l._member = await ctx.member(l.member_id);
      } catch {
        l._member = null;
      }
    }),
  );
  return items;
}

function reserveLoanColumns({ withMember = false, actions, feeOf } = {}) {
  const columns = [{ label: "ID", value: (l) => String(l.id) }];
  if (withMember) {
    columns.push({ label: "Member", value: (l) => (l._member ? link(`${l._member.member_no} ${l._member.full_name}`, `#/mem-03/${l._member.id}`) : `#${l.member_id}`) });
  }
  columns.push(
    { label: "Title", value: (l) => l.book_title },
    { label: "Course", value: (l) => l.course_code },
    { label: "Barcode", value: (l) => l._copy?.barcode ?? `#${l.copy_id}` },
    { label: "Lent at", value: (l) => fmtDateTime(l.lent_at) },
    { label: "Due at", value: (l) => fmtDateTime(l.due_at) },
    { label: "Status", value: (l) => l.status },
    { label: "Overdue", value: (l) => fmtBool(l.is_overdue) },
    { label: "Renewed", value: (l) => fmtBool(l.renewed) },
    { label: "Returned at", value: (l) => fmtDateTime(l.returned_at) },
    { label: "Late minutes", value: (l) => fmtText(l.late_minutes) },
    {
      label: "Late fee",
      value: (l) => {
        if (l.status === "open") return fmtAmount(l.accrued_late_fee);
        const fee = feeOf?.(l);
        return fee ? `${fmtAmount(fee.amount)} (${fee.status})` : "–";
      },
    },
  );
  if (actions) columns.push({ label: "Actions", value: (l) => actions(l) });
  return columns;
}

const overdueRow = (l) => (l.status === "open" && l.is_overdue ? "overdue" : undefined);

// ---- LIB-UI-CRS-01 ---------------------------------------------------------------

const coursesScreen = {
  id: "crs-01",
  title: "Courses",
  module: "Course reserves",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const map = await branchMap(ctx);
    const branches = await ctx.branches();
    const formBox = h("div", { class: "course-form" });
    const loansBox = h("div", { class: "course-open-loans" });

    const term = field({ name: "term", label: "Term", hint: "For example 2026-fall." });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const instructorNo = field({ name: "member_no", label: "Instructor member number" });
    const status = field({ name: "status", label: "Status", options: choices(COURSE_STATUSES, { any: "Any" }) });
    const q = field({ name: "q", label: "Code or title contains" });

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Code", value: (c) => c.code },
        { label: "Title", value: (c) => c.title },
        { label: "Term", value: (c) => c.term },
        { label: "Branch", value: (c) => branchName(map, c.branch_id) },
        { label: "Instructor", value: (c) => c._instructor },
        { label: "Dates", value: (c) => `${fmtDate(c.starts_on)} to ${fmtDate(c.ends_on)}` },
        { label: "Enrolled", value: (c) => `${c.enrolled} of ${c.enrollment_limit}` },
        { label: "Items", value: (c) => String(c.items) },
        { label: "Copies on reserve", value: (c) => String(c.copies_on_reserve) },
        { label: "Status", value: (c) => c.status },
        {
          label: "Actions",
          value: (c) =>
            h(
              "span",
              { class: "row-actions" },
              c.status !== "closed" ? button("Edit", () => openForm(c)) : null,
              c.status === "draft" ? button("Activate", () => activate(c)) : null,
              c.status !== "closed" ? button("Close", () => closeCourse(c)) : null,
              link("Enrollment", `#/crs-02/${c.id}`),
              link("Reading list", `#/crs-03/${c.id}`),
            ),
        },
      ],
      load: async (page) => {
        const query = { page, page_size: 20, term: term.input.value.trim(), branch_id: branch.input.value, status: status.input.value, q: q.input.value.trim() };
        if (instructorNo.input.value.trim()) query.instructor_id = (await findMember(instructorNo.input.value)).id;
        const data = await get("/courses", query);
        await withInstructors(ctx, data.items);
        return data;
      },
    });
    const reload = () => list.reload();

    function activate(c) {
      return ctx.act(() => post(`/courses/${c.id}/activate`), `Course ${c.code} activated.`, reload);
    }

    async function showOpenLoans(course) {
      const data = await get("/reserve-loans", { course_id: course.id, status: "open", page_size: 100 });
      await reserveLoanRows(ctx, data.items);
      replace(
        loansBox,
        section(
          `Open reserve loans of ${course.code}`,
          table({ columns: reserveLoanColumns({ withMember: true }), rows: data.items, rowClass: overdueRow }),
          button("Close", () => replace(loansBox)),
        ),
      );
    }

    function closeCourse(c) {
      ctx.ask({
        text: `Close course ${c.code}? Its copies on reserve are taken off reserve.`,
        onConfirm: () =>
          ctx.act(
            () => post(`/courses/${c.id}/close`),
            (r) => `Course ${r.code} closed. Released copies: ${r.released_copies}.`,
            async () => {
              replace(loansBox);
              await reload();
            },
            async (error) => {
              ctx.clearConfirmation();
              if (error.code === "COURSE_HAS_OPEN_LOANS") {
                try {
                  await showOpenLoans(c);
                } catch (inner) {
                  ctx.fail(inner);
                }
              }
            },
          ),
      });
    }

    async function openForm(course = null) {
      ctx.clearMessages();
      replace(loansBox);
      const editing = Boolean(course);
      let instructorValue = "";
      if (editing) {
        try {
          instructorValue = (await ctx.member(course.instructor_id)).member_no;
        } catch {
          instructorValue = "";
        }
      }
      const f = {};
      if (!editing) {
        f.code = field({ name: "code", label: "Code", hint: "2–4 letters and 3 digits, for example CENG301." });
        f.term = field({ name: "term", label: "Term", hint: "<year>-fall, <year>-spring or <year>-summer." });
        f.branch_id = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { activeOnly: true }) });
      }
      f.title = field({ name: "title", label: "Title", value: course?.title });
      f.member_no = field({ name: "member_no", label: "Instructor member number", value: instructorValue, hint: "An academic member." });
      f.starts_on = field({ name: "starts_on", label: "Starts on", type: "date", value: course ? fmtDate(course.starts_on) : "" });
      f.ends_on = field({ name: "ends_on", label: "Ends on", type: "date", value: course ? fmtDate(course.ends_on) : "", hint: "6 to 179 days after the start." });
      f.enrollment_limit = field({ name: "enrollment_limit", label: "Enrollment limit", type: "number", min: 1, max: 300, value: course?.enrollment_limit ?? "", hint: "1–300; 100 when empty." });
      const node = form({
        fields: Object.values(f),
        submit: editing ? "Save" : "Create",
        label: editing ? "Change course" : "New course",
        extra: button("Close", () => replace(formBox)),
        async onSubmit(v) {
          node.fieldErrors({});
          ctx.clearMessages();
          let instructor;
          try {
            instructor = await findMember(v.member_no);
          } catch (error) {
            ctx.fail(error);
            node.fieldErrors({ member_no: error.message });
            return;
          }
          const onError = (error) => node.fieldErrors(fieldProblems(error));
          const done = async () => {
            replace(formBox);
            await reload();
          };
          if (editing) {
            const body = {};
            if (v.title.trim() !== course.title) body.title = v.title.trim();
            if (instructor.id !== course.instructor_id) body.instructor_id = instructor.id;
            if (v.starts_on !== fmtDate(course.starts_on)) body.starts_on = v.starts_on;
            if (v.ends_on !== fmtDate(course.ends_on)) body.ends_on = v.ends_on;
            if (String(int(v.enrollment_limit)) !== String(course.enrollment_limit)) body.enrollment_limit = int(v.enrollment_limit);
            await ctx.act(() => patch(`/courses/${course.id}`, body), "Course saved.", done, onError);
            return;
          }
          const body = omitNull({
            code: v.code.trim(),
            title: v.title.trim(),
            term: v.term.trim(),
            instructor_id: instructor.id,
            branch_id: Number(v.branch_id),
            starts_on: v.starts_on,
            ends_on: v.ends_on,
            enrollment_limit: int(v.enrollment_limit),
          });
          await ctx.act(() => post("/courses", body), (c) => `Course ${c.code} created as draft.`, done, onError);
        },
      });
      replace(formBox, section(editing ? `Change course ${course.code}` : "New course", node));
      (f.code || f.title).input.focus();
    }

    const filters = form({
      fields: [term, branch, instructorNo, status, q],
      submit: "Filter",
      label: "Course filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return list.goTo(1);
      },
    });
    replace(ctx.body, h("div", { class: "actions" }, button("New course", () => openForm())), formBox, filters, loansBox, list.el);
    await list.goTo(1);
  },
};

// ---- LIB-UI-CRS-02 ---------------------------------------------------------------

const enrollmentScreen = {
  id: "crs-02",
  title: "Enrollment",
  module: "Course reserves",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const id = courseIdFromParam(ctx);
    if (id === null) {
      replace(ctx.body, coursePicker(ctx, await fetchAll("/courses"), "crs-02"));
      return;
    }
    const map = await branchMap(ctx);
    const info = h("div", { class: "course-info" });
    const resultBox = h("div", { class: "enroll-result" });
    let course = null;

    async function loadCourse() {
      course = await get(`/courses/${id}`);
      replace(info, section(`Course ${course.code}`, courseFacts(course, map, await memberText(ctx, course.instructor_id))));
    }

    const statusFilter = field({ name: "status", label: "Status", options: choices(ENROLLMENT_STATUSES, { any: "Any" }) });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Member number", value: (e) => link(e.member_no, `#/mem-03/${e.member_id}`) },
        { label: "Full name", value: (e) => e.full_name },
        { label: "Status", value: (e) => e.status },
        { label: "Enrolled at", value: (e) => fmtDateTime(e.enrolled_at) },
        { label: "Dropped at", value: (e) => fmtDateTime(e.dropped_at) },
        { label: "Drop reason", value: (e) => (e.drop_reason ? words(e.drop_reason) : "–") },
        {
          label: "Actions",
          value: (e) =>
            e.status === "enrolled"
              ? button("Drop", () =>
                  ctx.ask({
                    text: `Drop ${e.full_name} (${e.member_no}) from ${course.code}?`,
                    onConfirm: () =>
                      ctx.act(
                        () => post(`/enrollments/${e.id}/drop`),
                        `${e.full_name} dropped.`,
                        reloadAll,
                        () => ctx.clearConfirmation(),
                      ),
                  }),
                )
              : "–",
        },
      ],
      load: (page) => get(`/courses/${id}/enrollments`, { page, page_size: 20, status: statusFilter.input.value }),
    });
    const reloadAll = async () => {
      await loadCourse();
      await list.reload();
    };

    // ---- enroll: paste or pick member numbers
    const pasted = field({
      name: "member_nos",
      label: "Member numbers",
      type: "textarea",
      rows: 5,
      hint: "Paste member numbers, one per line or separated by commas.",
    });
    const pick = field({ name: "member_no", label: "Pick a member", hint: "Member number; the member is added to the list above." });

    function showResult(resolvedById, unknown, result) {
      const person = (memberId) => resolvedById.get(memberId);
      replace(
        resultBox,
        section(
          "Enrollment result",
          table({
            caption: "Enrolled",
            columns: [
              { label: "Member number", value: (m) => m.member_no },
              { label: "Full name", value: (m) => m.full_name },
            ],
            rows: result.enrolled.map(person).filter(Boolean),
          }),
          table({
            caption: "Skipped",
            columns: [
              { label: "Member number", value: (s) => s.member_no },
              { label: "Full name", value: (s) => s.full_name },
              { label: "Reason", value: (s) => `${s.error_code} (${words(s.error_code).toLowerCase()})` },
            ],
            rows: [
              ...unknown.map((no) => ({ member_no: no, full_name: "–", error_code: "NOT_FOUND" })),
              ...result.skipped.map((s) => ({
                member_no: person(s.member_id)?.member_no ?? `#${s.member_id}`,
                full_name: person(s.member_id)?.full_name ?? "–",
                error_code: s.error_code,
              })),
            ],
          }),
        ),
      );
    }

    const enrollForm = form({
      fields: [pasted],
      submit: "Enroll",
      label: "Enroll members",
      async onSubmit(v) {
        ctx.clearMessages();
        const seen = new Set();
        const tokens = v.member_nos
          .split(/[\s,;]+/)
          .filter(Boolean)
          .filter((t) => (seen.has(t.toLowerCase()) ? false : seen.add(t.toLowerCase())));
        if (!tokens.length) {
          ctx.fail(clientError("VALIDATION_ERROR", "Enter at least one member number.", { fields: [{ field: "member_nos", problem: "field required" }] }));
          return;
        }
        const resolvedById = new Map();
        const unknown = [];
        for (const token of tokens) {
          try {
            const m = await findMember(token);
            resolvedById.set(m.id, m);
          } catch (error) {
            if (error.code === "NOT_FOUND") unknown.push(token);
            else throw error;
          }
        }
        if (!resolvedById.size) {
          showResult(resolvedById, unknown, { enrolled: [], skipped: [] });
          ctx.ok("Nobody was enrolled.");
          return;
        }
        await ctx.act(
          () => post(`/courses/${id}/enrollments`, { member_ids: [...resolvedById.keys()] }),
          (r) => `Enrolled ${r.enrolled.length}, skipped ${r.skipped.length + unknown.length}.`,
          async (r) => {
            showResult(resolvedById, unknown, r);
            pasted.input.value = "";
            await reloadAll();
          },
        );
      },
    });
    const pickForm = form({
      fields: [pick],
      submit: "Add to list",
      label: "Pick a member",
      async onSubmit(v) {
        ctx.clearMessages();
        try {
          const m = await findMember(v.member_no);
          const current = pasted.input.value.trim();
          pasted.input.value = current ? `${current}\n${m.member_no}` : m.member_no;
          pick.input.value = "";
        } catch (error) {
          ctx.fail(error);
        }
      },
    });
    const filter = form({
      fields: [statusFilter],
      submit: "Filter",
      label: "Enrollment filters",
      cls: "filters",
      onSubmit: () => list.goTo(1),
    });

    replace(ctx.body, info, section("Enroll students", enrollForm, pickForm), resultBox, section("Enrollments", filter, list.el));
    await loadCourse();
    await list.goTo(1);
  },
};

// ---- LIB-UI-CRS-03 ---------------------------------------------------------------

const readingListScreen = {
  id: "crs-03",
  title: "Reading list",
  module: "Course reserves",
  roles: ["librarian", "admin", "member"],
  desk: true,
  async render(ctx) {
    const id = courseIdFromParam(ctx);
    if (id === null) {
      let courses;
      if (ctx.isStaff) {
        courses = await fetchAll("/courses");
      } else {
        const me = await get("/members/me");
        courses = (await fetchAll(`/members/${me.id}/courses`)).filter((c) => c.role === "instructor");
      }
      replace(ctx.body, coursePicker(ctx, courses, "crs-03"));
      return;
    }
    const map = await branchMap(ctx);
    const info = h("div", { class: "course-info" });
    const itemsBox = h("div", { class: "reading-items" });
    const editBox = h("div", { class: "item-editor" });
    let course = null;
    let items = [];

    async function loadCourse() {
      course = await get(`/courses/${id}`);
      replace(info, section(`Course ${course.code}`, courseFacts(course, map, await memberText(ctx, course.instructor_id))));
    }

    async function reorder(ids) {
      return ctx.act(() => api("PUT", `/courses/${id}/reading-list/order`, { body: { item_ids: ids } }), "Reading list reordered.", loadItems);
    }

    function move(item, delta) {
      const ids = items.map((i) => i.id);
      const from = ids.indexOf(item.id);
      const to = from + delta;
      if (to < 0 || to >= ids.length) return undefined;
      ids.splice(from, 1);
      ids.splice(to, 0, item.id);
      return reorder(ids);
    }

    function openEdit(item) {
      ctx.clearMessages();
      const kind = field({ name: "kind", label: "Kind", options: choices(ITEM_KINDS), value: item.kind });
      const period = field({ name: "loan_period", label: "Loan period", options: LOAN_PERIODS, value: item.loan_period });
      const wanted = field({ name: "copies_wanted", label: "Copies wanted", type: "number", min: 1, max: 5, value: item.copies_wanted });
      const note = field({ name: "note", label: "Note", value: item.note, hint: "Up to 500 characters." });
      const node = form({
        fields: [kind, period, wanted, note],
        submit: "Save",
        label: "Change item",
        extra: button("Close", () => replace(editBox)),
        async onSubmit(v) {
          node.fieldErrors({});
          const body = {};
          if (v.kind !== item.kind) body.kind = v.kind;
          if (v.loan_period !== item.loan_period) body.loan_period = v.loan_period;
          if (String(int(v.copies_wanted)) !== String(item.copies_wanted)) body.copies_wanted = int(v.copies_wanted);
          if (v.note !== item.note) body.note = v.note;
          await ctx.act(
            () => patch(`/reading-list-items/${item.id}`, body),
            "Item saved.",
            async () => {
              replace(editBox);
              await loadItems();
            },
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      replace(editBox, section(`Change ${item.book_title}`, node));
      kind.input.focus();
    }

    function removeItem(item) {
      ctx.ask({
        text: `Remove "${item.book_title}" from the reading list? Its copies on reserve are taken off reserve.`,
        onConfirm: () => ctx.act(() => post(`/reading-list-items/${item.id}/remove`), "Item removed.", loadItems, () => ctx.clearConfirmation()),
      });
    }

    function renderItems() {
      const wrap = table({
        columns: [
          { label: "Position", value: (i) => String(i.position) },
          { label: "Title", value: (i) => link(i.book_title, `#/cat-02/${i.book_id}`) },
          { label: "Kind", value: (i) => i.kind },
          { label: "Loan period", value: (i) => periodLabel(i.loan_period) },
          { label: "Copies wanted", value: (i) => String(i.copies_wanted) },
          { label: "Copies on reserve", value: (i) => String(i.copies_on_reserve) },
          { label: "Available now", value: (i) => String(i.available_now) },
          { label: "Next due", value: (i) => (i.next_due_at ? fmtDateTime(i.next_due_at) : "–") },
          { label: "Status", value: (i) => words(i.status) },
          { label: "Note", value: (i) => fmtText(i.note) },
          {
            label: "Actions",
            value: (i) =>
              h(
                "span",
                { class: "row-actions" },
                button("Move up", () => move(i, -1), { disabled: items[0] === i }),
                button("Move down", () => move(i, 1), { disabled: items[items.length - 1] === i }),
                button("Change", () => openEdit(i)),
                button("Remove", () => removeItem(i)),
              ),
          },
        ],
        rows: items,
      });
      // Drag and drop on the rows; "Move up" and "Move down" do the same with the keyboard.
      let dragged = null;
      const rows = wrap.querySelectorAll("tbody tr");
      if (items.length) {
        rows.forEach((tr, index) => {
          const item = items[index];
          tr.draggable = true;
          tr.classList.add("draggable");
          tr.addEventListener("dragstart", (event) => {
            dragged = item.id;
            event.dataTransfer?.setData("text/plain", String(item.id));
            if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
          });
          tr.addEventListener("dragover", (event) => {
            if (dragged !== null) event.preventDefault();
          });
          tr.addEventListener("drop", (event) => {
            event.preventDefault();
            if (dragged === null || dragged === item.id) return;
            const ids = items.map((i) => i.id);
            const draggedBefore = ids.indexOf(dragged) < ids.indexOf(item.id);
            ids.splice(ids.indexOf(dragged), 1);
            ids.splice(ids.indexOf(item.id) + (draggedBefore ? 1 : 0), 0, dragged);
            dragged = null;
            reorder(ids).catch((error) => ctx.fail(error));
          });
          tr.addEventListener("dragend", () => {
            dragged = null;
          });
        });
      }
      replace(itemsBox, h("p", { class: "hint" }, "Drag the rows to change the order, or use Move up and Move down."), wrap);
    }

    async function loadItems() {
      items = await fetchAll(`/courses/${id}/reading-list`);
      renderItems();
      await loadCourse();
    }

    // ---- add books from search
    const q = field({ name: "q", label: "Search the catalog", hint: "Title, author, publisher or ISBN." });
    const kind = field({ name: "kind", label: "Kind", options: choices(ITEM_KINDS) });
    const period = field({ name: "loan_period", label: "Loan period", options: LOAN_PERIODS });
    const wanted = field({ name: "copies_wanted", label: "Copies wanted", type: "number", min: 1, max: 5, value: "1" });
    const note = field({ name: "note", label: "Note" });
    const defaults = h("div", { class: "form inline-form add-defaults" }, kind, period, wanted, note);
    const results = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Title", value: (r) => link(r.book.title, `#/cat-02/${r.book.id}`) },
        { label: "Authors", value: (r) => r.book.authors.map((a) => a.name).join(", ") },
        { label: "Year", value: (r) => String(r.book.publication_year) },
        { label: "ISBN", value: (r) => r.book.isbn },
        {
          label: "Actions",
          value: (r) =>
            button("Add", () => {
              const v = values(defaults);
              return ctx.act(
                () =>
                  post(`/courses/${id}/reading-list`, omitNull({
                    book_id: r.book.id,
                    kind: v.kind,
                    loan_period: v.loan_period,
                    copies_wanted: int(v.copies_wanted),
                    note: text(v.note) ?? "",
                  })),
                (item) =>
                  `Added "${item.book_title}"${item.copies_on_reserve ? `; ${item.copies_on_reserve} copy/copies placed on reserve` : ""}.`,
                loadItems,
              );
            }),
        },
      ],
      load: (page) => get("/search/books", { page, page_size: 10, q: q.input.value.trim() }),
    });
    const searchBox = h("div", { class: "book-results" });
    const searchForm = form({
      fields: [q],
      submit: "Search",
      label: "Search books",
      onSubmit() {
        ctx.clearMessages();
        replace(searchBox, results.el);
        return results.goTo(1);
      },
    });

    replace(ctx.body, info, section("Reading list", itemsBox), editBox, section("Add books", searchForm, defaults, searchBox));
    await loadItems();
  },
};

// ---- LIB-UI-CRS-04 ---------------------------------------------------------------

async function openReserveLoanOfBarcode(barcode) {
  const wanted = String(barcode ?? "").trim();
  if (!wanted) throw clientError("VALIDATION_ERROR", "Enter a barcode.", { fields: [{ field: "barcode", problem: "field required" }] });
  const copy = await get(`/copies/by-barcode/${encodeURIComponent(wanted)}`);
  const loans = await fetchAll("/reserve-loans", { status: "open" });
  const loan = loans.find((l) => l.copy_id === copy.id);
  if (!loan) throw clientError("RESERVE_LOAN_NOT_OPEN", `Copy ${copy.barcode} has no open reserve loan.`, { barcode: copy.barcode });
  return loan;
}

async function loanFees(loan) {
  const fees = await fetchAll("/fees", { member_id: loan.member_id });
  return fees.filter((f) => f.reserve_loan_id === loan.id);
}

const reserveDeskScreen = {
  id: "crs-04",
  title: "Reserve desk",
  module: "Course reserves",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const resultBox = h("div", { class: "scan-result" });
    const placeBox = h("div", { class: "place-box" });

    const courses = [...(await fetchAll("/courses", { status: "active" })), ...(await fetchAll("/courses", { status: "draft" }))];
    const courseOptions = courses.length ? recordOptions(courses, courseLabel) : [{ value: "", label: "No courses" }];

    // ---- lend, return, renew, report lost by barcode
    const memberNo = field({ name: "member_no", label: "Member number", hint: "Needed for lending." });
    const barcode = field({ name: "barcode", label: "Barcode", attrs: { autocomplete: "off" } });
    const returnBranch = field({
      name: "branch_id",
      label: "Return branch",
      options: [{ value: "", label: "Branch of the course" }, ...branchOptions(branches, { activeOnly: true })],
    });

    async function summary(loan, extra = []) {
      const fees = loan.status === "open" ? [] : await loanFees(loan);
      return section(
        `Reserve loan ${loan.id}`,
        definitionList([
          ["Title", loan.book_title],
          ["Course", loan.course_code],
          ["Status", loan.status],
          ["Due at", fmtDateTime(loan.due_at)],
          ["Returned at", fmtDateTime(loan.returned_at)],
          ["Late minutes", fmtText(loan.late_minutes)],
          ...extra,
        ]),
        fees.length
          ? table({
              columns: [
                { label: "Fee", value: (f) => String(f.id) },
                { label: "Kind", value: (f) => words(f.kind) },
                { label: "Amount", value: (f) => fmtAmount(f.amount) },
                { label: "Status", value: (f) => f.status },
              ],
              rows: fees,
            })
          : null,
      );
    }

    const showSummary = async (loan, extra) => replace(resultBox, await summary(loan, extra));
    const afterScan = async (loan) => {
      await showSummary(loan);
      barcode.input.value = "";
      await loans.reload();
    };

    async function scanAction(run, text) {
      ctx.clearMessages();
      let loan;
      try {
        loan = await openReserveLoanOfBarcode(barcode.input.value);
      } catch (error) {
        ctx.fail(error);
        return;
      }
      await ctx.act(() => run(loan), text, afterScan);
    }

    const scanForm = form({
      fields: [memberNo, barcode, returnBranch],
      submit: "Lend",
      label: "Scan a barcode",
      extra: [
        button("Return", () =>
          scanAction(
            async (loan) => {
              const branchId = returnBranch.input.value ? Number(returnBranch.input.value) : (await get(`/courses/${loan.course_id}`)).branch_id;
              return post(`/reserve-loans/${loan.id}/return`, { branch_id: branchId });
            },
            (l) => `Returned. Late minutes: ${l.late_minutes ?? 0}.`,
          ),
        ),
        button("Renew", () =>
          scanAction(
            (loan) => post(`/reserve-loans/${loan.id}/renew`),
            (l) => `Renewed. New due time: ${fmtDateTime(l.due_at)}.`,
          ),
        ),
        button("Report lost", () =>
          scanAction(
            (loan) => post(`/reserve-loans/${loan.id}/report-lost`),
            "Reserve loan reported lost.",
          ),
        ),
      ],
      async onSubmit(v) {
        ctx.clearMessages();
        let member;
        try {
          member = await findMember(v.member_no);
        } catch (error) {
          ctx.fail(error);
          return;
        }
        await ctx.act(
          () => post("/reserve-loans", { member_id: member.id, barcode: v.barcode.trim() }),
          (l) => `Lent to ${member.full_name}. Due at ${fmtDateTime(l.due_at)}.`,
          async (l) => {
            await showSummary(l);
            barcode.input.value = "";
            await loans.reload();
          },
        );
      },
    });

    // ---- place copies on reserve / take them off
    const placeCourse = field({ name: "course_id", label: "Course", options: courseOptions });
    const placeItem = field({ name: "item_id", label: "Reading list item", options: [{ value: "", label: "No items" }] });
    const placeBarcode = field({ name: "barcode", label: "Barcode of the copy" });

    async function loadItems() {
      const cid = placeCourse.input.value;
      let items = [];
      if (cid) {
        try {
          items = await fetchAll(`/courses/${cid}/reading-list`);
        } catch (error) {
          ctx.fail(error);
        }
      }
      placeItem.input.replaceChildren(
        ...(items.length
          ? items.map((i) => h("option", { value: String(i.id) }, `${i.position}. ${i.book_title} (${i.copies_on_reserve} of ${i.copies_wanted} on reserve)`))
          : [h("option", { value: "" }, "No items")]),
      );
    }
    placeCourse.input.addEventListener("change", loadItems);

    const placeForm = form({
      fields: [placeCourse, placeItem, placeBarcode],
      submit: "Place on reserve",
      label: "Place a copy on reserve",
      async onSubmit(v) {
        ctx.clearMessages();
        try {
          if (!v.item_id) throw clientError("VALIDATION_ERROR", "Choose a reading list item.", { fields: [{ field: "item_id", problem: "field required" }] });
          const copy = await get(`/copies/by-barcode/${encodeURIComponent(v.barcode.trim())}`);
          await ctx.act(
            () => post(`/reading-list-items/${v.item_id}/copies`, { copy_id: copy.id }),
            (r) => `Copy ${r.barcode} placed on reserve.`,
            async () => {
              placeBarcode.input.value = "";
              await loadItems();
            },
          );
        } catch (error) {
          ctx.fail(error);
        }
      },
    });

    const offBarcode = field({ name: "barcode", label: "Barcode of the copy" });
    const offForm = form({
      fields: [offBarcode],
      submit: "Take off reserve",
      label: "Take a copy off reserve",
      async onSubmit(v) {
        ctx.clearMessages();
        try {
          const copy = await get(`/copies/by-barcode/${encodeURIComponent(v.barcode.trim())}`);
          ctx.ask({
            text: `Take copy ${copy.barcode} off reserve?`,
            onConfirm: () =>
              ctx.act(
                () => post(`/copies/${copy.id}/unreserve`),
                `Copy ${copy.barcode} taken off reserve.`,
                async () => {
                  offBarcode.input.value = "";
                  await loadItems();
                },
                () => ctx.clearConfirmation(),
              ),
          });
        } catch (error) {
          ctx.fail(error);
        }
      },
    });

    // ---- reserve loans
    const allCourses = await fetchAll("/courses");
    const loanCourse = field({ name: "course_id", label: "Course", options: recordOptions(allCourses, courseLabel, { any: "All courses" }) });
    const loanStatus = field({ name: "status", label: "Status", options: choices(LOAN_STATUSES, { any: "Any" }), value: "open" });
    const loanOverdue = field({ name: "overdue", label: "Overdue", options: BOOLEAN });
    let feeMap = new Map();
    const loans = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: reserveLoanColumns({
        withMember: true,
        feeOf: (l) => feeMap.get(l.fee_id),
        actions: (l) =>
          l.status !== "open"
            ? "–"
            : h(
                "span",
                { class: "row-actions" },
                button("Renew", () => ctx.act(() => post(`/reserve-loans/${l.id}/renew`), (r) => `Renewed. New due time: ${fmtDateTime(r.due_at)}.`, () => loans.reload())),
                button("Return", async () => {
                  const course = await get(`/courses/${l.course_id}`);
                  await ctx.act(
                    () => post(`/reserve-loans/${l.id}/return`, { branch_id: course.branch_id }),
                    (r) => `Returned. Late minutes: ${r.late_minutes ?? 0}.`,
                    async (r) => {
                      await showSummary(r);
                      await loans.reload();
                    },
                  );
                }),
                button("Report lost", () =>
                  ctx.act(
                    () => post(`/reserve-loans/${l.id}/report-lost`),
                    "Reserve loan reported lost.",
                    async (r) => {
                      await showSummary(r);
                      await loans.reload();
                    },
                  ),
                ),
              ),
      }),
      rowClass: overdueRow,
      load: async (page) => {
        const data = await get("/reserve-loans", {
          page,
          page_size: 20,
          course_id: loanCourse.input.value,
          status: loanStatus.input.value,
          overdue: loanOverdue.input.value,
        });
        await reserveLoanRows(ctx, data.items);
        const closed = data.items.filter((l) => l.fee_id);
        feeMap = new Map();
        for (const memberId of new Set(closed.map((l) => l.member_id))) {
          try {
            for (const f of await fetchAll("/fees", { member_id: memberId })) feeMap.set(f.id, f);
          } catch {
            // fees are shown when they can be read
          }
        }
        return data;
      },
    });
    const loanFilters = form({
      fields: [loanCourse, loanStatus, loanOverdue],
      submit: "Filter",
      label: "Reserve loan filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return loans.goTo(1);
      },
    });

    const processButton = button("Process", () =>
      ctx.act(
        () => post("/course-reserves/process"),
        (r) =>
          `Processed. Overdue notices: ${r.overdue_notices}. Closed courses: ${r.closed_courses}. Released copies: ${r.released_copies}. Pending courses: ${r.pending_courses}.`,
        async () => {
          await loans.reload();
          await loadItems();
        },
      ),
    );

    replace(
      ctx.body,
      section("Lend, return, renew or report lost", scanForm, resultBox),
      section("Copies on reserve", placeForm, offForm),
      section("Reserve loans", loanFilters, loans.el),
      h("div", { class: "actions" }, processButton),
    );
    await Promise.all([loadItems(), loans.goTo(1)]);
  },
};

// ---- LIB-UI-CRS-05 ---------------------------------------------------------------

const myCoursesScreen = {
  id: "crs-05",
  title: "My courses",
  module: "Course reserves",
  roles: ["member"],
  async render(ctx) {
    const map = await branchMap(ctx);
    const me = await get("/members/me");
    const coursesBox = h("div", { class: "my-courses" });
    const loansBox = h("div", { class: "my-reserve-loans" });
    let feeMap = new Map();

    async function loadCourses() {
      const courses = await fetchAll(`/members/${me.id}/courses`);
      if (!courses.length) {
        replace(coursesBox, table({ columns: [{ label: "Course", value: (c) => c.code }], rows: [] }));
        return;
      }
      const blocks = [];
      for (const course of courses) {
        const items = await fetchAll(`/courses/${course.id}/reading-list`);
        blocks.push(
          section(
            `${course.code} – ${course.title}`,
            definitionList([
              ["Term", course.term],
              ["Role", course.role],
              ["Branch", branchName(map, course.branch_id)],
              course.role === "instructor" ? ["Instructor", me.full_name] : null,
              ["Dates", `${fmtDate(course.starts_on)} to ${fmtDate(course.ends_on)}`],
              ["Status", course.status],
            ].filter(Boolean)),
            course.role === "instructor" ? link("Edit the reading list", `#/crs-03/${course.id}`) : null,
            table({
              caption: "Reading list",
              columns: [
                { label: "Title", value: (i) => link(i.book_title, `#/cat-02/${i.book_id}`) },
                { label: "Kind", value: (i) => i.kind },
                { label: "Loan period", value: (i) => periodLabel(i.loan_period) },
                { label: "Copies on reserve", value: (i) => String(i.copies_on_reserve) },
                { label: "Available now", value: (i) => String(i.available_now) },
                { label: "Next due", value: (i) => (i.next_due_at ? fmtDateTime(i.next_due_at) : "–") },
              ],
              rows: items,
            }),
          ),
        );
      }
      replace(coursesBox, blocks);
    }

    const loans = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: reserveLoanColumns({
        feeOf: (l) => feeMap.get(l.fee_id),
        actions: (l) =>
          l.status === "open"
            ? button("Renew", () => ctx.act(() => post(`/reserve-loans/${l.id}/renew`), (r) => `Renewed. New due time: ${fmtDateTime(r.due_at)}.`, () => loans.reload()))
            : "–",
      }),
      rowClass: overdueRow,
      load: async (page) => {
        const data = await get(`/members/${me.id}/reserve-loans`, { page, page_size: 10 });
        await reserveLoanRows(ctx, data.items);
        feeMap = new Map((await fetchAll(`/members/${me.id}/fees`)).map((f) => [f.id, f]));
        return data;
      },
    });
    replace(loansBox, loans.el);

    replace(ctx.body, section("Courses", coursesBox), section("Reserve loans", loansBox));
    await Promise.all([loadCourses(), loans.goTo(1)]);
  },
};

// ---- LIB-UI-CRS-06 ---------------------------------------------------------------

const courseReportScreen = {
  id: "crs-06",
  title: "Course reserves report",
  module: "Course reserves",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const from = field({ name: "from", label: "From", type: "date", value: addDays(ctx.today, -29) });
    const to = field({ name: "to", label: "To", type: "date", value: ctx.today });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "All branches" }) });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Code", value: (r) => link(r.code, `#/crs-03/${r.course_id}`) },
        { label: "Title", value: (r) => r.title },
        { label: "Term", value: (r) => r.term },
        { label: "Status", value: (r) => r.status },
        { label: "Enrolled", value: (r) => String(r.enrolled) },
        { label: "Items", value: (r) => String(r.items) },
        { label: "Items unfilled", value: (r) => String(r.items_unfilled) },
        { label: "Loans", value: (r) => String(r.loans) },
        { label: "Borrowers", value: (r) => String(r.borrowers) },
        { label: "Late returns", value: (r) => String(r.late_returns) },
        { label: "Fees charged", value: (r) => fmtAmount(r.fees_charged) },
      ],
      load: (page) =>
        get("/reports/course-reserves", { page, page_size: 20, from: from.input.value, to: to.input.value, branch_id: branch.input.value }),
    });
    const node = form({
      fields: [from, to, branch],
      submit: "Show",
      label: "Course reserves report",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return list.goTo(1);
      },
    });
    replace(ctx.body, node, list.el);
    await list.goTo(1);
  },
};

export const courseScreens = [
  coursesScreen,
  enrollmentScreen,
  readingListScreen,
  reserveDeskScreen,
  myCoursesScreen,
  courseReportScreen,
];
