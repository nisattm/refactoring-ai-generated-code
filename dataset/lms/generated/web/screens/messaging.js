// Module: Announcements and messages (module 27): announcements, member feed, inbox, my messages, report, header badges.

import { fetchAll, get, patch, post } from "../api.js";
import { findMember } from "../context.js";
import {
  BOOLEAN_FILTER,
  branchOptions,
  button,
  choices,
  definitionList,
  dash,
  field,
  fieldProblems,
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
  uid,
  words,
} from "../ui.js";
import { branchMap, branchName } from "../views.js";

const MODULE = "Announcements and messages";
// Library time is fixed at UTC+03:00 (LIB-COM-01); request date-times carry that offset.
const OFFSET = "+03:00";

const MEMBERSHIP_TYPES = ["student", "academic", "staff", "guest"];
const AUDIENCE_ALIASES = { students: "student", academics: "academic", guests: "guest" };
const PRIORITIES = ["normal", "important"];
const ANNOUNCEMENT_STATUSES = ["draft", "published", "withdrawn"];
const CATEGORIES = ["general", "loan", "fee", "room", "other"];
const THREAD_STATUSES = ["open", "answered", "closed"];
const REOPENABLE = new Set(["member_request", "staff_request", "inactive"]);

// ---- helpers ---------------------------------------------------------------------

/** The value of a `datetime-local` input for an API date-time ("2026-11-03T09:00:00+03:00"). */
const toInput = (value) => (value ? String(value).slice(0, 16) : "");
/** The API date-time for the value of a `datetime-local` input. */
const toStamp = (value) => `${value.length === 16 ? `${value}:00` : value}${OFFSET}`;
const audienceKey = (value) => AUDIENCE_ALIASES[value] || value;
const audienceText = (list) => list.map((x) => words(audienceKey(x))).join(", ");
const plural = (count, one, many = `${one}s`) => `${count} ${count === 1 ? one : many}`;
const percent = (value) => (value === null || value === undefined ? dash : `${value} %`);

function checkField({ name, label, checked = false, hint }) {
  const id = uid(name);
  const input = h("input", { id, name, type: "checkbox" });
  input.checked = checked;
  const errorBox = h("small", { class: "field-error", id: `${id}-error` });
  input.setAttribute("aria-describedby", errorBox.id);
  const wrap = h("div", { class: "field check-field" }, h("span", { class: "check" }, input, h("label", { for: id }, label)), hint ? h("small", { class: "hint" }, hint) : null, errorBox);
  wrap.input = input;
  wrap.setError = (problem) => {
    errorBox.textContent = problem || "";
    if (problem) input.setAttribute("aria-invalid", "true");
    else input.removeAttribute("aria-invalid");
  };
  return wrap;
}

/** The membership types of an announcement: one checkbox each, all with name `audience`. */
function audienceField(selected) {
  const chosen = new Set(selected.map(audienceKey));
  const legend = h("legend", {}, "Audience");
  const boxes = MEMBERSHIP_TYPES.map((type) => {
    const id = uid("audience");
    const input = h("input", { id, name: "audience", type: "checkbox", value: type });
    input.checked = chosen.has(type);
    return { type, input, node: h("span", { class: "check" }, input, h("label", { for: id }, words(type))) };
  });
  const errorBox = h("small", { class: "field-error", id: uid("audience-error") });
  const wrap = h("fieldset", { class: "field audience-group", "aria-describedby": errorBox.id }, legend, ...boxes.map((b) => b.node), errorBox);
  wrap.input = boxes[0].input;
  wrap.selected = () => boxes.filter((b) => b.input.checked).map((b) => b.type);
  wrap.setError = (problem) => {
    errorBox.textContent = problem || "";
  };
  return wrap;
}

function badge(label, kind) {
  return h("span", { class: `badge badge-${kind}` }, label);
}

// ---- LIB-UI-MSG-01 ---------------------------------------------------------------

function liveText(a) {
  if (a.status !== "published") return "No";
  if (a.live) return "Live";
  return a.scheduled ? "Scheduled" : "Expired";
}

function announcementFields({ announcement, branches }) {
  const a = announcement;
  const branchList = branchOptions(branches, { activeOnly: true });
  if (a && a.branch_id !== null && !branchList.some((o) => String(o.value) === String(a.branch_id))) {
    branchList.push(...branchOptions(branches.filter((b) => b.id === a.branch_id)));
  }
  return {
    title: field({ name: "title", label: "Title", value: a?.title ?? "", required: true, attrs: { maxlength: "200" } }),
    body: field({ name: "body", label: "Body", type: "textarea", rows: 6, value: a?.body ?? "", required: true, attrs: { maxlength: "5000" } }),
    branch_id: field({ name: "branch_id", label: "Branch", options: [{ value: "", label: "All branches" }, ...branchList], value: a?.branch_id ?? "" }),
    audience: audienceField(a ? a.audience : MEMBERSHIP_TYPES),
    priority: field({ name: "priority", label: "Priority", options: choices(PRIORITIES), value: a?.priority ?? "normal" }),
    pinned: checkField({ name: "pinned", label: "Pinned", checked: a?.pinned ?? false, hint: "At most 3 pinned announcements are live per branch." }),
    publish_at: field({
      name: "publish_at",
      label: "Publish at",
      type: "datetime-local",
      value: toInput(a?.publish_at),
      hint: "Leave empty for now; a later time schedules the announcement.",
    }),
    expires_at: field({
      name: "expires_at",
      label: "Expires at",
      type: "datetime-local",
      value: toInput(a?.expires_at),
      hint: "Optional; at most 90 days after the publish time.",
    }),
  };
}

const announcementsScreen = {
  id: "msg-01",
  title: "Announcements",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const map = await branchMap(ctx);
    const formBox = h("div", { class: "announcement-form" });
    const statsBox = h("div", { class: "announcement-stats" });

    const status = field({ name: "status", label: "Status", options: choices(ANNOUNCEMENT_STATUSES, { any: "Any" }) });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const live = field({ name: "live", label: "Live now", options: BOOLEAN_FILTER });
    const scheduled = field({ name: "scheduled", label: "Scheduled", options: BOOLEAN_FILTER });

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "ID", value: (a) => String(a.id) },
        { label: "Title", value: (a) => a.title },
        { label: "Branch", value: (a) => (a.branch_id === null ? "All branches" : branchName(map, a.branch_id)) },
        { label: "Audience", value: (a) => audienceText(a.audience) },
        { label: "Priority", value: (a) => a.priority },
        { label: "Pinned", value: (a) => fmtBool(a.pinned) },
        { label: "Publish at", value: (a) => fmtDateTime(a.publish_at) },
        { label: "Expires at", value: (a) => fmtDateTime(a.expires_at) },
        { label: "Status", value: (a) => a.status },
        { label: "Live", value: (a) => liveText(a) },
        {
          label: "Actions",
          value: (a) =>
            h(
              "span",
              { class: "row-actions" },
              a.status !== "withdrawn" ? button("Edit", () => openForm(a)) : null,
              a.status === "draft" ? button("Publish", () => publish(a)) : null,
              a.status === "published" ? button("Withdraw", () => withdraw(a)) : null,
              a.status === "published" ? button("Reach", () => showStats(a)) : null,
            ),
        },
      ],
      load: (page) =>
        get("/announcements", {
          page,
          page_size: 20,
          status: status.input.value,
          branch_id: branch.input.value,
          live: live.input.value,
          scheduled: scheduled.input.value,
        }),
    });
    const reload = () => list.reload();

    function publish(a) {
      return ctx.act(() => post(`/announcements/${a.id}/publish`), (r) => `Announcement "${r.title}" published.`, reload);
    }

    function withdraw(a) {
      ctx.ask({
        text: `Withdraw the announcement "${a.title}"? Members no longer see it, and a withdrawn announcement cannot be published again.`,
        onConfirm: () => ctx.act(() => post(`/announcements/${a.id}/withdraw`), "Announcement withdrawn.", reload),
      });
    }

    async function showStats(a) {
      await ctx.act(
        () => get(`/announcements/${a.id}/stats`),
        null,
        (s) =>
          replace(
            statsBox,
            section(
              `Reach and reads: ${a.title}`,
              definitionList([
                ["Audience size", String(s.audience_size)],
                ["Reads", String(s.reads)],
                ["Read rate", percent(s.read_rate)],
              ]),
              button("Close", () => replace(statsBox)),
            ),
          ),
      );
    }

    function openForm(a = null) {
      ctx.clearMessages();
      const f = announcementFields({ announcement: a, branches });
      const node = form({
        fields: Object.values(f),
        submit: a ? "Save" : "Create",
        label: a ? "Change announcement" : "New announcement",
        extra: button("Close", () => replace(formBox)),
        async onSubmit(v) {
          node.fieldErrors({});
          const onError = (error) => node.fieldErrors(fieldProblems(error));
          const audience = f.audience.selected();
          const branchId = int(v.branch_id);
          const done = async () => {
            replace(formBox);
            await reload();
          };
          if (a) {
            const body = {};
            if (v.title.trim() !== a.title) body.title = v.title.trim();
            if (v.body !== a.body) body.body = v.body;
            if (branchId !== a.branch_id) body.branch_id = branchId;
            if ([...audience].sort().join() !== a.audience.map(audienceKey).sort().join()) body.audience = audience;
            if (v.priority !== a.priority) body.priority = v.priority;
            if (v.pinned !== a.pinned) body.pinned = v.pinned;
            if (v.publish_at && v.publish_at !== toInput(a.publish_at)) body.publish_at = toStamp(v.publish_at);
            if (v.expires_at !== toInput(a.expires_at)) body.expires_at = v.expires_at ? toStamp(v.expires_at) : null;
            if (!Object.keys(body).length) {
              ctx.ok("There is nothing to save: no value was changed.");
              return;
            }
            await ctx.act(() => patch(`/announcements/${a.id}`, body), "Announcement saved.", done, onError);
            return;
          }
          const body = omitNull({
            title: v.title.trim(),
            body: v.body,
            branch_id: branchId,
            audience,
            priority: v.priority,
            pinned: v.pinned,
            publish_at: v.publish_at ? toStamp(v.publish_at) : null,
            expires_at: v.expires_at ? toStamp(v.expires_at) : null,
          });
          // omitNull also drops a null branch_id, which is the default "all branches"
          await ctx.act(() => post("/announcements", body), (r) => `Announcement ${r.id} created as draft.`, done, onError);
        },
      });
      replace(formBox, section(a ? `Change announcement ${a.id}: ${a.title}` : "New announcement", node));
      f.title.input.focus();
    }

    const filters = form({
      fields: [status, branch, live, scheduled],
      submit: "Filter",
      label: "Announcement filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return list.goTo(1);
      },
    });
    const processButton = button("Process", () => runProcess(ctx, reload));
    replace(
      ctx.body,
      h("div", { class: "actions" }, button("New announcement", () => openForm()), processButton),
      h("p", { class: "hint" }, "Process releases announcements whose publish time has come and closes answered threads that have been inactive for 14 days."),
      formBox,
      statsBox,
      filters,
      list.el,
    );
    await list.goTo(1);
  },
};

/** POST /messaging/process (LIB-MSG-07, LIB-MSG-28, LIB-MSG-42). */
function runProcess(ctx, after) {
  return ctx.act(
    () => post("/messaging/process"),
    (r) => `Processed: ${plural(r.announcements_released, "announcement")} released, ${plural(r.threads_closed, "thread")} closed.`,
    after,
  );
}

// ---- LIB-UI-MSG-02 (part of the home screen) -------------------------------------

/** The live announcements of the member: pinned first, unread marked, with the unread counter. */
export async function memberAnnouncements(ctx) {
  const list = pagedTable({
    onError: (e) => ctx.fail(e),
    rowClass: (a) => (a.read ? undefined : "unread"),
    columns: [
      {
        label: "Announcement",
        value: (a) =>
          h(
            "div",
            { class: "announcement" },
            h("strong", { class: "announcement-title" }, a.title),
            " ",
            a.pinned ? badge("Pinned", "pinned") : null,
            a.priority === "important" ? badge("Important", "important") : null,
            h("p", { class: "announcement-body" }, a.body),
          ),
      },
      { label: "Published", value: (a) => fmtDate(a.publish_at) },
      { label: "Read", value: (a) => (a.read ? "Read" : h("strong", { class: "unread-mark" }, "Unread")) },
      { label: "Actions", value: (a) => (a.read ? dash : button("Mark as read", () => markRead(a))) },
    ],
    extraAbove: (data) => h("p", { class: "unread-counter" }, "Unread announcements: ", h("strong", { class: "unread-count" }, String(data.unread))),
    load: (page) => get("/announcements", { page, page_size: 5 }),
  });
  function markRead(a) {
    return ctx.act(() => post(`/announcements/${a.id}/read`), "Announcement marked as read.", () => list.reload());
  }
  await list.goTo(1);
  return section("Announcements", list.el);
}

const memberHomeScreen = {
  id: "msg-02",
  title: "Member home",
  module: MODULE,
  roles: ["member"],
  part: true,
  async render(ctx) {
    replace(ctx.body, h("p", {}, "Announcements are shown on the home screen."));
  },
};

// ---- threads: shared parts -------------------------------------------------------

function messageList(thread, { staffView }) {
  const items = (thread.messages || []).map((m) => {
    const mine = staffView ? m.author === "staff" : m.author === "member";
    let who;
    if (staffView) who = m.author === "member" ? thread.member?.full_name || "Member" : `Staff (user ${m.user_id})`;
    else who = mine ? "You" : "Library staff";
    return h(
      "li",
      { class: `thread-message from-${m.author}${m.internal ? " internal" : ""}${mine ? " mine" : ""}` },
      h(
        "div",
        { class: "thread-message-head" },
        h("strong", {}, who),
        " ",
        h("time", {}, fmtDateTime(m.created_at)),
        m.internal ? badge("Internal note", "internal") : null,
        !m.internal && m.read_at ? h("small", { class: "hint" }, ` Read ${fmtDateTime(m.read_at)}`) : null,
      ),
      h("p", { class: "thread-message-body" }, m.body),
    );
  });
  return h("ol", { class: "thread-messages", "aria-label": "Messages" }, items.length ? items : h("li", {}, "No messages"));
}

function replyForm(ctx, thread, { staff, after }) {
  const body = field({ name: "body", label: "Message", type: "textarea", rows: 4, required: true, attrs: { maxlength: "2000" } });
  const internal = staff ? checkField({ name: "internal", label: "Internal note", hint: "Only staff see internal notes; the member is not notified." }) : null;
  const node = form({
    fields: internal ? [body, internal] : [body],
    submit: "Reply",
    label: "Reply",
    cls: "reply-form",
    async onSubmit(v) {
      node.fieldErrors({});
      const note = staff && v.internal === true;
      await ctx.act(
        () => post(`/threads/${thread.id}/messages`, staff ? { body: v.body, internal: note } : { body: v.body }),
        note ? "Internal note added." : "Reply sent.",
        after,
        (error) => node.fieldErrors(fieldProblems(error)),
      );
    },
  });
  return node;
}

// ---- LIB-UI-MSG-03 ---------------------------------------------------------------

async function assigneeDirectory(ctx) {
  const names = new Map();
  if (ctx.isAdmin) {
    try {
      const users = await fetchAll("/users", { is_active: "true" });
      for (const u of users) if (u.role === "librarian" || u.role === "admin") names.set(u.id, u.full_name);
    } catch {
      // the numeric field of the assign form still works
    }
  }
  names.set(ctx.user.id, ctx.user.full_name);
  return {
    names,
    name(id) {
      if (id === null || id === undefined) return dash;
      const name = names.get(id) || `User ${id}`;
      return id === ctx.user.id ? `${name} (you)` : name;
    },
  };
}

const inboxScreen = {
  id: "msg-03",
  title: "Inbox",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const map = await branchMap(ctx);
    const people = await assigneeDirectory(ctx);
    const threadBox = h("div", { class: "thread-view" });

    const status = field({ name: "status", label: "Status", options: choices(THREAD_STATUSES, { any: "Any" }) });
    const assigned = field({
      name: "assigned_to",
      label: "Assigned to",
      options: [
        { value: "", label: "Anybody" },
        { value: "me", label: "Me (mine)" },
      ],
    });
    const overdue = field({ name: "overdue", label: "Overdue", options: BOOLEAN_FILTER });
    const category = field({ name: "category", label: "Category", options: choices(CATEGORIES, { any: "Any" }) });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const memberNo = field({ name: "member_no", label: "Member number", hint: "For example M000001." });

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      rowClass: (t) => (t.unread ? "unread" : undefined),
      columns: [
        { label: "ID", value: (t) => String(t.id) },
        { label: "Subject", value: (t) => t.subject },
        { label: "Member", value: (t) => (t._member ? `${t._member.member_no} ${t._member.full_name}` : `#${t.member_id}`) },
        { label: "Category", value: (t) => t.category },
        { label: "Branch", value: (t) => branchName(map, t.branch_id) },
        { label: "Status", value: (t) => t.status },
        { label: "Assigned to", value: (t) => people.name(t.assigned_to) },
        { label: "Due at", value: (t) => fmtDateTime(t.due_at) },
        { label: "Overdue", value: (t) => (t.is_overdue ? `Yes, ${t.overdue_by_hours} h` : "No") },
        { label: "Unread", value: (t) => String(t.unread) },
        { label: "Last message", value: (t) => fmtDateTime(t.last_message_at) },
        { label: "Actions", value: (t) => button("Open", () => openThread(t.id)) },
      ],
      load: async (page) => {
        const wanted = memberNo.input.value.trim();
        const member = wanted ? await findMember(wanted) : null;
        const data = await get("/threads", {
          page,
          page_size: 20,
          status: status.input.value,
          assigned_to: assigned.input.value,
          overdue: overdue.input.value,
          category: category.input.value,
          branch_id: branch.input.value,
          member_id: member ? member.id : "",
        });
        await Promise.all(
          data.items.map(async (t) => {
            try {
              t._member = await ctx.member(t.member_id);
            } catch {
              t._member = null;
            }
          }),
        );
        return data;
      },
    });

    async function refresh(id) {
      const thread = await get(`/threads/${id}`);
      showThread(thread);
      await list.reload();
    }

    function openThread(id) {
      return ctx.act(
        () => get(`/threads/${id}`),
        null,
        (thread) => {
          showThread(thread);
          threadBox.scrollIntoView?.({ block: "nearest" });
          return list.reload();
        },
      );
    }

    function showThread(t) {
      const closed = t.status === "closed";
      const after = () => refresh(t.id);
      const member = t.member;
      const facts = [
        ["Member", member ? h("span", {}, link(member.member_no, `#/mem-03/${member.id}`), ` ${member.full_name} (${words(member.membership_type)})`) : `#${t.member_id}`],
        ["Branch", branchName(map, t.branch_id)],
        ["Category", t.category],
        ["Status", t.status],
        ["Assigned to", people.name(t.assigned_to)],
        ["Created", fmtDateTime(t.created_at)],
        ["Due at", fmtDateTime(t.due_at)],
        ["Overdue", t.is_overdue ? `Yes, by ${t.overdue_by_hours} h` : "No"],
        ["First reply", fmtDateTime(t.first_reply_at)],
      ];
      if (t.loan) facts.push(["Loan", `${t.loan.id}, ${t.loan.status}, due ${fmtDate(t.loan.due_date)}`]);
      if (t.fee) facts.push(["Fee", `${t.fee.id}, ${words(t.fee.kind)}, ${t.fee.amount} TL, ${t.fee.status}`]);
      if (closed) {
        facts.push(["Closed", fmtDateTime(t.closed_at)], ["Close reason", t.close_reason ? words(t.close_reason) : dash], ["Rating", t.rating === null ? "Not rated" : `${t.rating} of 5`]);
      }
      const parts = [definitionList(facts), messageList(t, { staffView: true })];
      if (!closed) {
        parts.push(replyForm(ctx, t, { staff: true, after }), assignForm(t, after));
        parts.push(h("div", { class: "actions" }, button("Close", () => askClose(t, after))));
      }
      parts.push(h("div", { class: "actions" }, button("Hide", () => replace(threadBox))));
      replace(threadBox, section(`Thread ${t.id}: ${t.subject}`, ...parts));
    }

    function askClose(t, after) {
      ctx.ask({
        text: `Close the thread "${t.subject}"? The member can reopen it within 14 days.`,
        onConfirm: () => ctx.act(() => post(`/threads/${t.id}/close`), "Thread closed.", after),
      });
    }

    function assignForm(t, after) {
      const users = [...people.names.entries()];
      const user = ctx.isAdmin
        ? field({ name: "user_id", label: "Staff member", options: [{ value: "", label: "Nobody" }, ...recordOptions(users.map(([id, name]) => ({ id, name })), (u) => u.name)], value: t.assigned_to ?? "" })
        : field({ name: "user_id", label: "User ID", type: "number", min: 1, value: t.assigned_to ?? "", hint: "The ID of a librarian or admin user; empty removes the assignment." });
      const assign = (userId, text) => ctx.act(() => post(`/threads/${t.id}/assign`, { user_id: userId }), text, after);
      const node = form({
        fields: [user],
        submit: "Assign",
        label: "Assign",
        cls: "assign-form",
        extra: h("span", { class: "row-actions" }, button("Assign to me", () => assign(ctx.user.id, "Thread assigned to you.")), button("Unassign", () => assign(null, "Assignment removed."))),
        async onSubmit(v) {
          node.fieldErrors({});
          const id = int(v.user_id);
          await assign(id, id === null ? "Assignment removed." : "Thread assigned.");
        },
      });
      return node;
    }

    const filters = form({
      fields: [status, assigned, overdue, category, branch, memberNo],
      submit: "Filter",
      label: "Thread filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return list.goTo(1);
      },
    });
    replace(ctx.body, h("div", { class: "actions" }, button("Process", () => runProcess(ctx, () => list.reload()))), filters, list.el, threadBox);
    await list.goTo(1);
    if (/^\d+$/.test(ctx.param)) await openThread(Number(ctx.param));
  },
};

// ---- LIB-UI-MSG-04 ---------------------------------------------------------------

const myMessagesScreen = {
  id: "msg-04",
  title: "My messages",
  module: MODULE,
  roles: ["member"],
  desk: false,
  async render(ctx) {
    const map = await branchMap(ctx);
    const branches = await ctx.branches();
    const memberId = ctx.user.member_id;
    const threadBox = h("div", { class: "thread-view" });
    const formBox = h("div", { class: "thread-form" });

    const status = field({ name: "status", label: "Status", options: choices(THREAD_STATUSES, { any: "Any" }) });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      rowClass: (t) => (t.unread ? "unread" : undefined),
      columns: [
        { label: "Subject", value: (t) => t.subject },
        { label: "Category", value: (t) => t.category },
        { label: "Branch", value: (t) => branchName(map, t.branch_id) },
        { label: "Status", value: (t) => t.status },
        { label: "Unread replies", value: (t) => (t.unread ? h("strong", { class: "unread-mark" }, String(t.unread)) : "0") },
        { label: "Last message", value: (t) => fmtDateTime(t.last_message_at) },
        { label: "Actions", value: (t) => button("Open", () => openThread(t.id)) },
      ],
      load: (page) => get("/threads", { page, page_size: 20, status: status.input.value }),
    });

    async function refresh(id) {
      showThread(await get(`/threads/${id}`));
      await list.reload();
    }

    function openThread(id) {
      return ctx.act(
        () => get(`/threads/${id}`),
        null,
        (thread) => {
          showThread(thread);
          threadBox.scrollIntoView?.({ block: "nearest" });
          return list.reload();
        },
      );
    }

    function showThread(t) {
      const closed = t.status === "closed";
      const after = () => refresh(t.id);
      const facts = [
        ["Branch", branchName(map, t.branch_id)],
        ["Category", t.category],
        ["Status", t.status],
        ["Created", fmtDateTime(t.created_at)],
      ];
      if (t.loan_id !== null) facts.push(["Loan", String(t.loan_id)]);
      if (t.fee_id !== null) facts.push(["Fee", String(t.fee_id)]);
      if (closed) facts.push(["Closed", fmtDateTime(t.closed_at)], ["Close reason", t.close_reason ? words(t.close_reason) : dash]);
      if (t.rating !== null) facts.push(["Your rating", `${t.rating} of 5`]);
      const parts = [definitionList(facts), messageList(t, { staffView: false })];
      if (!closed) {
        parts.push(replyForm(ctx, t, { staff: false, after }));
        parts.push(
          h(
            "div",
            { class: "actions" },
            button("Close", () =>
              ctx.ask({
                text: `Close the thread "${t.subject}"? You can reopen it within 14 days.`,
                onConfirm: () => ctx.act(() => post(`/threads/${t.id}/close`), "Thread closed.", after),
              }),
            ),
          ),
        );
      } else {
        const actions = h("div", { class: "actions" });
        if (REOPENABLE.has(t.close_reason)) {
          actions.append(button("Reopen", () => ctx.act(() => post(`/threads/${t.id}/reopen`), "Thread reopened.", after)));
        }
        parts.push(actions);
        if (t.rating === null && (t.messages || []).some((m) => m.author === "staff")) parts.push(ratingForm(t, after));
      }
      parts.push(h("div", { class: "actions" }, button("Hide", () => replace(threadBox))));
      replace(threadBox, section(`${t.subject}`, ...parts));
    }

    function ratingForm(t, after) {
      const rating = field({ name: "rating", label: "Rating", options: [1, 2, 3, 4, 5].map((n) => ({ value: n, label: `${n} of 5` })), value: 5 });
      const node = form({
        fields: [rating],
        submit: "Rate",
        label: "Rate",
        cls: "rating-form",
        async onSubmit(v) {
          node.fieldErrors({});
          await ctx.act(() => post(`/threads/${t.id}/rate`, { rating: Number(v.rating) }), "Thank you for your rating.", after, (e) => node.fieldErrors(fieldProblems(e)));
        },
      });
      return node;
    }

    async function openNewForm() {
      ctx.clearMessages();
      let loans = [];
      let fees = [];
      let home = "";
      try {
        const me = await get("/members/me");
        home = me.home_branch_id ?? "";
      } catch {
        // the branch is simply not preselected
      }
      try {
        loans = await fetchAll(`/members/${memberId}/loans`);
        await Promise.all(
          loans.map(async (l) => {
            try {
              l._book = await ctx.book((await ctx.copy(l.copy_id)).book_id);
            } catch {
              l._book = null;
            }
          }),
        );
      } catch {
        loans = [];
      }
      try {
        fees = await fetchAll(`/members/${memberId}/fees`);
      } catch {
        fees = [];
      }
      const active = branchOptions(branches, { activeOnly: true });
      const f = {
        branch_id: field({ name: "branch_id", label: "Branch", options: active, value: active.some((o) => String(o.value) === String(home)) ? home : active[0]?.value }),
        subject: field({ name: "subject", label: "Subject", required: true, attrs: { maxlength: "200" } }),
        category: field({ name: "category", label: "Category", options: choices(CATEGORIES) }),
        loan_id: field({
          name: "loan_id",
          label: "Loan",
          options: [{ value: "", label: "No loan" }, ...recordOptions(loans, (l) => `#${l.id} ${l._book ? l._book.title : `copy ${l.copy_id}`}, due ${fmtDate(l.due_date)} (${l.status})`)],
          hint: "Only for the category loan.",
        }),
        fee_id: field({
          name: "fee_id",
          label: "Fee",
          options: [{ value: "", label: "No fee" }, ...recordOptions(fees, (x) => `#${x.id} ${words(x.kind)}, ${x.amount} TL (${x.status})`)],
          hint: "Only for the category fee.",
        }),
        body: field({ name: "body", label: "Message", type: "textarea", rows: 5, required: true, attrs: { maxlength: "2000" } }),
      };
      const node = form({
        fields: Object.values(f),
        submit: "Send",
        label: "New message",
        extra: button("Close", () => replace(formBox)),
        async onSubmit(v) {
          node.fieldErrors({});
          const body = omitNull({
            branch_id: int(v.branch_id),
            subject: v.subject.trim(),
            category: v.category,
            loan_id: int(v.loan_id),
            fee_id: int(v.fee_id),
            body: v.body,
          });
          await ctx.act(
            () => post("/threads", body),
            "Message sent.",
            (t) => {
              replace(formBox);
              showThread(t);
              return list.reload();
            },
            (error) => node.fieldErrors(fieldProblems(error)),
          );
        },
      });
      replace(formBox, section("Write to the library", node));
      f.subject.input.focus();
    }

    const filters = form({
      fields: [status],
      submit: "Filter",
      label: "Thread filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        return list.goTo(1);
      },
    });
    replace(ctx.body, h("div", { class: "actions" }, button("New message", openNewForm)), formBox, filters, list.el, threadBox);
    await list.goTo(1);
    if (/^\d+$/.test(ctx.param)) await openThread(Number(ctx.param));
  },
};

// ---- LIB-UI-MSG-05 ---------------------------------------------------------------

function addDays(isoDate, days) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

const messagingReportScreen = {
  id: "msg-05",
  title: "Messaging report",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const from = field({ name: "from", label: "From", type: "date", value: addDays(ctx.today, -29) });
    const to = field({ name: "to", label: "To", type: "date", value: ctx.today });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "All branches" }) });
    const result = h("div", { class: "report-result" });

    async function load() {
      const r = await get("/reports/messaging", { from: from.input.value, to: to.input.value, branch_id: branch.input.value });
      const rows = [
        ["Threads", String(r.threads)],
        ...CATEGORIES.map((c) => [`Threads: ${c}`, String(r.by_category[c])]),
        ["Answered", String(r.answered)],
        ["Average first reply (hours)", fmtText(r.average_first_reply_hours)],
        ["Overdue now", String(r.overdue_now)],
        ["Closed", String(r.closed)],
        ["Average rating", fmtText(r.average_rating)],
        ["Announcements published", String(r.announcements.published)],
        ["Important announcements", String(r.announcements.important)],
        ["Announcement reads", String(r.announcements.reads)],
      ];
      replace(
        result,
        table({
          caption: `Threads created from ${from.input.value} to ${to.input.value}`,
          columns: [
            { label: "Measure", value: (row) => row[0] },
            { label: "Value", value: (row) => row[1] },
          ],
          rows,
        }),
      );
    }

    const node = form({
      fields: [from, to, branch],
      submit: "Show",
      label: "Messaging report",
      cls: "filters",
      async onSubmit() {
        await ctx.act(load, null, null, () => replace(result));
      },
    });
    replace(ctx.body, node, result);
    await ctx.act(load, null, null, () => replace(result));
  },
};

// ---- LIB-UI-MSG-06 (part of the header) ------------------------------------------

/**
 * Counters of the header (LIB-UI-GEN-05): {announcements, replies, announcementsHref, repliesHref}.
 * Members: LIB-MSG-33 (`messages` of the summary). Staff have no read marks for announcements (always 0);
 * their unread replies are the member messages of open threads that nobody has read yet.
 */
export async function headerCounts(user) {
  if (user.role === "member") {
    if (!user.member_id) return null;
    const summary = await get(`/members/${user.member_id}/summary`);
    return { announcements: summary.messages.unread_announcements, replies: summary.messages.unread_replies, announcementsHref: "#/home", repliesHref: "#/msg-04" };
  }
  const data = await get("/threads", { status: "open", page_size: 100 });
  return { announcements: 0, replies: data.items.reduce((sum, t) => sum + t.unread, 0), announcementsHref: "#/msg-01", repliesHref: "#/msg-03" };
}

const headerBadgesScreen = {
  id: "msg-06",
  title: "Header badges",
  module: MODULE,
  roles: ["all"],
  part: true,
  async render(ctx) {
    replace(ctx.body, h("p", {}, "The unread announcement and reply counters are shown in the page header."));
  },
};

export const messagingScreens = [announcementsScreen, memberHomeScreen, inboxScreen, myMessagesScreen, messagingReportScreen, headerBadgesScreen];
