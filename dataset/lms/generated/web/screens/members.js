// Module 3: members.

import { get, patch, post } from "../api.js";
import { memberPageParts } from "../registry.js";
import {
  BOOLEAN_FILTER,
  branchOptions,
  button,
  choices,
  definitionList,
  field,
  fieldProblems,
  fmtDate,
  fmtText,
  form,
  h,
  link,
  omitNull,
  pagedTable,
  replace,
  section,
  text,
  words,
} from "../ui.js";
import { borrowingBlock, summaryFacts } from "./home.js";
import {
  branchMap,
  branchName,
  feeColumns,
  loanColumns,
  memberLink,
  memberPicker,
  notificationColumns,
  reservationColumns,
  withBooks,
  withCopies,
} from "../views.js";

const TYPES = ["student", "academic", "staff", "guest"];
const STATUSES = ["active", "passive"];

export const memberFacts = (member, map) =>
  definitionList([
    ["Member number", member.member_no],
    ["Full name", member.full_name],
    ["Email", member.email],
    ["Phone", fmtText(member.phone)],
    ["Membership type", member.membership_type],
    ["University ID", fmtText(member.university_id)],
    ["Home branch", branchName(map, member.home_branch_id)],
    ["Status", member.status],
    ["Membership start", fmtDate(member.membership_start)],
    ["Valid until", `${fmtDate(member.valid_until)} (${member.membership_valid ? "valid" : "not valid"})`],
    ...(member.card_no !== undefined ? [["Card number", fmtText(member.card_no)]] : []),
  ]);

// ---- LIB-UI-MEM-01 ---------------------------------------------------------------

const memberListScreen = {
  id: "mem-01",
  title: "Member list",
  module: "Members",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const map = await branchMap(ctx);
    const q = field({ name: "q", label: "Search", hint: "Name, email, member number or university ID." });
    const type = field({ name: "membership_type", label: "Membership type", options: choices(TYPES, { any: "Any" }) });
    const status = field({ name: "status", label: "Status", options: choices(STATUSES, { any: "Any" }) });
    const branch = field({ name: "home_branch_id", label: "Home branch", options: branchOptions(branches, { any: "Any" }) });
    const valid = field({ name: "membership_valid", label: "Membership valid", options: BOOLEAN_FILTER });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      onRowClick: (m) => ctx.navigate(`#/mem-03/${m.id}`),
      columns: [
        { label: "Member number", value: (m) => memberLink(m) },
        { label: "Full name", value: (m) => m.full_name },
        { label: "Type", value: (m) => m.membership_type },
        { label: "Status", value: (m) => m.status },
        { label: "Valid until", value: (m) => fmtDate(m.valid_until) },
      ],
      load: (page) =>
        get("/members", {
          page,
          page_size: 20,
          q: q.input.value.trim(),
          membership_type: type.input.value,
          status: status.input.value,
          home_branch_id: branch.input.value,
          membership_valid: valid.input.value,
        }),
    });
    const filters = form({
      fields: [q, type, status, branch, valid],
      submit: "Filter",
      label: "Member filters",
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

// ---- LIB-UI-MEM-02 ---------------------------------------------------------------

function memberFields(branches, member = null) {
  return {
    full_name: field({ name: "full_name", label: "Full name", value: member?.full_name }),
    email: field({ name: "email", label: "Email", type: "email", value: member?.email }),
    phone: field({
      name: "phone",
      label: "Phone",
      value: member?.phone,
      hint: "Required for guests. Digits and spaces, optional leading +, 10–15 digits.",
    }),
    membership_type: field({
      name: "membership_type",
      label: "Membership type",
      options: choices(TYPES),
      value: member?.membership_type,
    }),
    university_id: field({
      name: "university_id",
      label: "University ID",
      value: member?.university_id,
      hint: "Required except for guests, who must leave it empty. 4–20 letters or digits, unique.",
    }),
    home_branch_id: field({
      name: "home_branch_id",
      label: "Home branch",
      options: branchOptions(branches, { activeOnly: !member }),
      value: member?.home_branch_id,
    }),
  };
}

const registerScreen = {
  id: "mem-02",
  title: "Register member",
  module: "Members",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const f = memberFields(branches);
    const password = field({
      name: "password",
      label: "Password",
      type: "password",
      autocomplete: "new-password",
      hint: "8–128 characters with at least one letter and one digit.",
    });
    const result = h("div", { class: "register-result" });
    const node = form({
      fields: [...Object.values(f), password],
      submit: "Register",
      label: "Register member",
      async onSubmit(v) {
        node.fieldErrors({});
        const member = await ctx.act(
          () =>
            post("/members", {
              full_name: v.full_name.trim(),
              email: v.email.trim(),
              phone: text(v.phone),
              membership_type: v.membership_type,
              university_id: text(v.university_id),
              home_branch_id: Number(v.home_branch_id),
              password: v.password,
            }),
          (m) => `Member registered. Member number: ${m.member_no}`,
          null,
          (error) => node.fieldErrors(fieldProblems(error)),
        );
        if (member) {
          replace(result, h("p", {}, "Member number ", h("strong", {}, member.member_no), ": ", link("Open member page", `#/mem-03/${member.id}`)));
          password.input.value = "";
        } else {
          replace(result);
        }
      },
    });
    replace(ctx.body, node, result);
  },
};

// ---- LIB-UI-MEM-03 ---------------------------------------------------------------

const memberPageScreen = {
  id: "mem-03",
  title: "Member page",
  module: "Members",
  roles: ["librarian", "admin"],
  async render(ctx) {
    const id = /^\d+$/.test(ctx.param) ? Number(ctx.param) : null;
    if (id === null) {
      replace(
        ctx.body,
        memberPicker(ctx, { onPick: (m) => ctx.navigate(`#/mem-03/${m.id}`) }),
      );
      return;
    }
    const map = await branchMap(ctx);
    const branches = await ctx.branches();
    const data = h("div", { class: "member-data" });
    const editor = h("div", { class: "member-editor" });
    const parts = h("div", { class: "member-parts" });
    const lists = h("div", { class: "member-lists" });
    let member = null;

    async function load() {
      const [m, summary] = await Promise.all([get(`/members/${id}`), get(`/members/${id}/summary`)]);
      member = m;
      replace(
        data,
        section("Member data", memberFacts(m, map)),
        section("Summary", summaryFacts(summary), borrowingBlock(summary)),
      );
    }

    function openEdit() {
      const f = memberFields(branches, member);
      const node = form({
        fields: Object.values(f),
        submit: "Save",
        label: "Edit member",
        extra: button("Close", () => replace(editor)),
        async onSubmit(v) {
          node.fieldErrors({});
          const body = omitNull({
            full_name: v.full_name.trim() !== member.full_name ? v.full_name.trim() : null,
            email: v.email.trim().toLowerCase() !== member.email ? v.email.trim() : null,
            phone: text(v.phone) !== member.phone ? text(v.phone) ?? "" : null,
            membership_type: v.membership_type !== member.membership_type ? v.membership_type : null,
            university_id: text(v.university_id) !== member.university_id ? text(v.university_id) ?? "" : null,
            home_branch_id: Number(v.home_branch_id) !== member.home_branch_id ? Number(v.home_branch_id) : null,
          });
          // A cleared optional text is sent as null.
          for (const key of ["phone", "university_id"]) if (body[key] === "") body[key] = null;
          const done = await ctx.act(
            () => patch(`/members/${id}`, body),
            "Member saved.",
            async () => {
              await load();
              await reloadLists();
              replace(editor);
            },
            (error) => node.fieldErrors(fieldProblems(error)),
          );
          return done;
        },
      });
      replace(editor, section("Edit member", node));
    }

    const actions = h(
      "div",
      { class: "actions member-actions" },
      button("Edit", openEdit),
      button("Renew membership", () => ctx.act(() => post(`/members/${id}/renew-membership`), "Membership renewed.", load)),
      button("Deactivate", () =>
        ctx.ask({
          text: "Deactivate this member? Their active reservations will be cancelled.",
          onConfirm: () => ctx.act(() => post(`/members/${id}/deactivate`), "Member deactivated.", async () => { await load(); await reloadLists(); }),
        }),
      ),
      button("Activate", () => ctx.act(() => post(`/members/${id}/activate`), "Member activated.", load)),
    );

    const loanList = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: loanColumns(),
      load: async (page) => {
        const d = await get(`/members/${id}/loans`, { page, page_size: 10 });
        await withCopies(ctx, d.items);
        return d;
      },
    });
    const reservationList = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: reservationColumns(map),
      load: async (page) => {
        const d = await get(`/members/${id}/reservations`, { page, page_size: 10 });
        await withBooks(ctx, d.items);
        return d;
      },
    });
    const feeList = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: feeColumns(),
      load: (page) => get(`/members/${id}/fees`, { page, page_size: 10 }),
    });
    const notificationList = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: notificationColumns(),
      load: (page) => get(`/members/${id}/notifications`, { page, page_size: 10 }),
    });
    const reloadLists = () => Promise.all([loanList.reload(), reservationList.reload(), feeList.reload(), notificationList.reload()]);
    replace(
      lists,
      section("Loans", loanList.el),
      section("Reservations", reservationList.el),
      section("Fees", feeList.el),
      section("Notifications", notificationList.el),
    );

    replace(ctx.body, data, actions, editor, lists, parts);
    await load();
    await Promise.all([loanList.goTo(1), reservationList.goTo(1), feeList.goTo(1), notificationList.goTo(1)]);
    for (const part of memberPageParts) {
      try {
        parts.append(await part.render(ctx, member));
      } catch (error) {
        ctx.fail(error);
      }
    }
  },
};

// ---- LIB-UI-MEM-04 ---------------------------------------------------------------

const myMembershipScreen = {
  id: "mem-04",
  title: "My membership",
  module: "Members",
  roles: ["member"],
  async render(ctx) {
    const map = await branchMap(ctx);
    const member = await get("/members/me");
    const summary = await get(`/members/${member.id}/summary`);
    replace(
      ctx.body,
      section("Member data", memberFacts(member, map)),
      section("Summary", summaryFacts(summary), borrowingBlock(summary)),
    );
  },
};

export const memberScreens = [memberListScreen, registerScreen, memberPageScreen, myMembershipScreen];
