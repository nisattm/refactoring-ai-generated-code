// LIB-UI-GEN-08: home screen.

import { get } from "../api.js";
import { definitionList, fmtAmount, fmtBool, fmtDate, h, replace, section } from "../ui.js";

export function borrowingBlock(summary) {
  const reasons = summary.borrowing.reasons;
  return h(
    "div",
    { class: "borrowing" },
    h("p", {}, "Borrowing: ", h("strong", {}, summary.borrowing.eligible ? "eligible" : "not eligible")),
    reasons.length ? h("ul", { class: "reasons" }, reasons.map((code) => h("li", {}, code))) : null,
  );
}

export function summaryFacts(summary) {
  const member = summary.member;
  return definitionList([
    ["Member number", member.member_no],
    ["Membership valid until", `${fmtDate(member.valid_until)} (${member.membership_valid ? "valid" : "not valid"})`],
    ["Open loans", String(summary.open_loans)],
    ["Overdue loans", String(summary.overdue_loans)],
    ["Active reservations", String(summary.active_reservations)],
    ["Outstanding fees", fmtAmount(summary.balance.outstanding_fees)],
    ["Accrued late fees", fmtAmount(summary.balance.accrued_late_fees)],
    ["Balance", fmtAmount(summary.balance.total_debt)],
    ["Blocked by debt", fmtBool(summary.balance.blocked)],
  ]);
}

export const homeScreen = {
  id: "home",
  title: "Home",
  roles: ["all"],
  async render(ctx) {
    if (ctx.isMember) {
      const member = await get("/members/me");
      const summary = await get(`/members/${member.id}/summary`);
      replace(ctx.body, section("My library account", summaryFacts(summary), borrowingBlock(summary)));
      return;
    }
    const desk = ctx.screens.filter((s) => s.desk);
    replace(
      ctx.body,
      section(
        "Desk screens",
        h("ul", { class: "desk-links" }, desk.map((s) => h("li", {}, h("a", { href: `#/${s.id}` }, s.title)))),
      ),
    );
  },
};
