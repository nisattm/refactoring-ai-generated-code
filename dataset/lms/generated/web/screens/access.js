// Module 28: member cards and building access (LIB-UI-ACC-01 to LIB-UI-ACC-06).

import { api, clientError, fetchAll, get, post } from "../api.js";
import { findMember } from "../context.js";
import {
  alertContent,
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
  text,
  words,
} from "../ui.js";
import { branchMap, branchName, memberLink, memberPicker } from "../views.js";

const MODULE = "Member cards and building access";
const isId = (value) => /^\d+$/.test(value || "");

const putJson = (path, body) => api("PUT", path, { body });

/** The member named by the route parameter (a member id), or null. */
async function paramMember(ctx) {
  return isId(ctx.param) ? ctx.member(Number(ctx.param)) : null;
}

const memberLine = (member) => h("p", { class: "member-line" }, "Member: ", memberLink(member), ` – ${member.full_name}`);

const needBranch = (value) =>
  value ? null : clientError("VALIDATION_ERROR", "Choose a branch.", { fields: [{ field: "branch_id", problem: "field required" }] });

// ---- LIB-UI-ACC-01 ---------------------------------------------------------------

const cardsScreen = {
  id: "acc-01",
  title: "Cards",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const member = await paramMember(ctx);
    const picker = memberPicker(ctx, {
      submit: "Open",
      value: member ? member.member_no : "",
      onPick: (m) => ctx.navigate(`#/acc-01/${m.id}`),
    });
    if (!member) {
      replace(ctx.body, section("Choose a member", picker));
      return;
    }

    const id = member.id;
    const resultBox = h("div", { class: "card-result" });
    const reportBox = h("div", { class: "card-report" });
    let allCards = [];
    let feeById = new Map();

    async function loadSide() {
      const [cards, fees] = await Promise.all([
        fetchAll(`/members/${id}/cards`),
        fetchAll(`/members/${id}/fees`, { kind: "card_replacement" }),
      ]);
      allCards = cards;
      feeById = new Map(fees.map((f) => [f.id, f]));
      drawReport();
    }

    const cardNo = (cardId) => {
      if (cardId === null || cardId === undefined) return "–";
      return allCards.find((c) => c.id === cardId)?.card_no || `card #${cardId}`;
    };
    const feeText = (card) => {
      if (card.fee_id === null) return "–";
      const fee = feeById.get(card.fee_id);
      return fee ? `${fmtAmount(fee.amount)} (${fee.status})` : `fee #${card.fee_id}`;
    };

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Card number", value: (c) => c.card_no },
        { label: "Status", value: (c) => c.status },
        { label: "Issued on", value: (c) => fmtDate(c.issued_on) },
        { label: "Expires on", value: (c) => fmtDate(c.expires_on) },
        { label: "Ended on", value: (c) => fmtDate(c.ended_on) },
        { label: "Replaces", value: (c) => cardNo(c.replaces_id) },
        { label: "Replacement fee", value: (c) => feeText(c) },
      ],
      load: async (page) => {
        await loadSide();
        return get(`/members/${id}/cards`, { page, page_size: 10 });
      },
    });

    function drawReport() {
      const active = allCards.find((c) => c.status === "active");
      const no = field({ name: "card_no", label: "Card number", value: active ? active.card_no : "", hint: "For example LC00000001." });
      const reason = field({ name: "reason", label: "Reason", options: choices(["lost", "damaged"]) });
      const node = form({
        fields: [no, reason],
        submit: "Report",
        label: "Report a card",
        async onSubmit(v) {
          node.fieldErrors({});
          const card = await ctx.act(
            () => post(`/cards/${encodeURIComponent(v.card_no.trim())}/report`, { reason: v.reason }),
            (c) => `Card ${c.card_no} reported ${c.status}.`,
            async () => {
              replace(resultBox);
              await list.reload();
            },
            (error) => node.fieldErrors(fieldProblems(error)),
          );
          return card;
        },
      });
      replace(reportBox, node);
    }

    function showIssued(card) {
      const fee = card.fee_id === null ? null : feeById.get(card.fee_id);
      replace(
        resultBox,
        definitionList([
          ["Card number", card.card_no],
          ["Status", card.status],
          ["Issued on", fmtDate(card.issued_on)],
          ["Expires on", fmtDate(card.expires_on)],
          ["Replaces", cardNo(card.replaces_id)],
          ["Replacement fee", card.fee_id === null ? "None" : fee ? fmtAmount(fee.amount) : `fee #${card.fee_id}`],
        ]),
      );
    }

    const issue = h(
      "div",
      { class: "actions" },
      button("Issue", async () => {
        const card = await ctx.act(
          () => post(`/members/${id}/cards`),
          (c) => `Card ${c.card_no} issued.`,
          () => list.reload(),
        );
        if (card) showIssued(card);
      }),
    );

    replace(
      ctx.body,
      section("Choose a member", picker),
      memberLine(member),
      section("Issue a card", h("p", { class: "hint" }, "A card replacing a lost or damaged one carries a replacement fee."), issue, resultBox),
      section("Report a card", reportBox),
      section("Card history", list.el),
    );
    await list.goTo(1);
  },
};

// ---- LIB-UI-ACC-02 ---------------------------------------------------------------

const gateScreen = {
  id: "acc-02",
  title: "Gate",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { activeOnly: true }) });
    const direction = field({ name: "direction", label: "Direction", options: choices(["in", "out"]) });
    const card = field({ name: "card_no", label: "Card number", hint: "For example LC00000001.", attrs: { autocomplete: "off" } });
    const pass = field({ name: "pass_code", label: "Pass code", hint: "For example DP-AA-20261102-1.", attrs: { autocomplete: "off" } });
    const result = h("div", { class: "gate-result-box" });
    const inside = h("p", { class: "gate-occupancy" });
    let ticket = 0;

    async function showOccupancy(branchId) {
      try {
        const o = await get(`/branches/${branchId}/occupancy`);
        replace(inside, `Inside now: ${o.inside}${o.capacity === null ? "" : ` of ${o.capacity}`}`);
      } catch {
        replace(inside);
      }
    }

    const node = form({
      fields: [branch, direction, card, pass],
      submit: "Scan",
      label: "Scan",
      cls: "gate-form",
      async onSubmit(v) {
        ctx.clearMessages();
        replace(result);
        const mine = (ticket += 1);
        try {
          const problem = needBranch(v.branch_id);
          if (problem) throw problem;
          const body = omitNull({
            branch_id: int(v.branch_id),
            direction: v.direction,
            card_no: text(v.card_no),
            pass_code: text(v.pass_code),
          });
          const done = await post("/access/scan", body);
          let who = body.pass_code || "";
          if (done.member_id !== null && done.member_id !== undefined) who = (await ctx.member(done.member_id)).full_name;
          if (mine !== ticket) return;
          replace(
            result,
            h("p", { class: "gate-result ok", role: "status" }, h("strong", {}, done.result), ": ", who),
          );
          card.input.value = "";
          pass.input.value = "";
          card.input.focus();
          showOccupancy(body.branch_id);
        } catch (error) {
          if (mine !== ticket) return;
          replace(result, h("div", { class: "gate-result bad", role: "alert" }, alertContent(error)));
        }
      },
    });
    replace(ctx.body, section("Scan a card or a day pass", node, result, inside));
  },
};

// ---- LIB-UI-ACC-03 ---------------------------------------------------------------

function settingsPanel(ctx, branchId, reloadAll) {
  const box = h("div", { class: "access-settings" });
  async function load() {
    const s = await get(`/access-settings/${branchId}`);
    if (!ctx.isAdmin) {
      replace(
        box,
        definitionList([
          ["Capacity", s.capacity === null ? "No limit" : String(s.capacity)],
          ["Guest entry", fmtBool(s.guest_entry)],
          ["Day passes", fmtBool(s.day_passes)],
          ["Day pass price", fmtAmount(s.day_pass_price)],
        ]),
      );
      return;
    }
    const capacity = field({ name: "capacity", label: "Capacity", type: "number", min: 1, max: 5000, value: s.capacity ?? "", hint: "Empty means no limit." });
    const guest = field({ name: "guest_entry", label: "Guest entry", options: [{ value: "true", label: "Yes" }, { value: "false", label: "No" }], value: String(s.guest_entry) });
    const passes = field({ name: "day_passes", label: "Day passes", options: [{ value: "true", label: "Yes" }, { value: "false", label: "No" }], value: String(s.day_passes) });
    const price = field({ name: "day_pass_price", label: "Day pass price", value: s.day_pass_price, hint: "0.00 to 100.00 TL." });
    const node = form({
      fields: [capacity, guest, passes, price],
      submit: "Save",
      label: "Access settings",
      async onSubmit(v) {
        node.fieldErrors({});
        await ctx.act(
          () =>
            putJson(`/access-settings/${branchId}`, {
              capacity: int(v.capacity),
              guest_entry: v.guest_entry === "true",
              day_passes: v.day_passes === "true",
              day_pass_price: v.day_pass_price.trim(),
            }),
          "Settings saved.",
          reloadAll,
          (error) => node.fieldErrors(fieldProblems(error)),
        );
      },
    });
    replace(box, node);
  }
  return { el: box, load };
}

const occupancyScreen = {
  id: "acc-03",
  title: "Occupancy",
  module: MODULE,
  roles: ["all"],
  async render(ctx) {
    const branches = await ctx.branches();
    const branch = field({
      name: "branch_id",
      label: "Branch",
      options: branchOptions(branches),
      value: isId(ctx.param) ? ctx.param : undefined,
    });
    const facts = h("div", { class: "occupancy-facts" });
    const insideBox = h("div", { class: "inside-box" });
    const settingsBox = h("div", { class: "settings-box" });
    const processBox = h("div", { class: "process-box" });
    const current = () => branch.input.value;
    const map = await branchMap(ctx);

    const inside = ctx.isStaff
      ? pagedTable({
          onError: (e) => ctx.fail(e),
          columns: [
            { label: "Visitor", value: (r) => (r.member_id === null ? "Day pass" : r.full_name) },
            { label: "Member", value: (r) => (r.member_id === null ? "–" : link(String(r.member_id), `#/mem-03/${r.member_id}`)) },
            { label: "Day pass", value: (r) => fmtText(r.day_pass_code) },
            { label: "Entered at", value: (r) => fmtDateTime(r.entered_at) },
            {
              label: "Actions",
              value: (r) =>
                button("End visit", () =>
                  ctx.act(() => post(`/visits/${r.visit_id}/close`), "Visit ended.", reloadAll),
                ),
            },
          ],
          load: (page) => get(`/branches/${current()}/inside`, { page, page_size: 20 }),
        })
      : null;

    async function loadFacts() {
      const o = await get(`/branches/${current()}/occupancy`);
      replace(
        facts,
        definitionList([
          ["Branch", branchName(map, o.branch_id)],
          ["Inside", String(o.inside)],
          ["Members", String(o.members)],
          ["Visitors", String(o.visitors)],
          ["Capacity", o.capacity === null ? "No limit" : String(o.capacity)],
          ["Free places", o.free === null ? "No limit" : String(o.free)],
        ]),
      );
    }

    async function reloadAll() {
      if (!current()) return;
      await loadFacts();
      if (inside) await inside.reload();
      if (ctx.isStaff) await showSettings();
    }

    async function showSettings() {
      const panel = settingsPanel(ctx, current(), reloadAll);
      await panel.load();
      replace(settingsBox, section(ctx.isAdmin ? "Access settings" : "Access settings of the branch", panel.el));
    }

    const node = form({
      fields: [branch],
      submit: "Show",
      label: "Choose a branch",
      async onSubmit() {
        ctx.clearMessages();
        ctx.clearConfirmation();
        if (!current()) {
          ctx.fail(needBranch(""));
          return;
        }
        try {
          await loadFacts();
          if (inside) await inside.goTo(1);
          if (ctx.isStaff) await showSettings();
        } catch (error) {
          ctx.fail(error);
        }
      },
    });
    branch.input.addEventListener("change", () => node.requestSubmit());

    replace(insideBox, ctx.isStaff ? section("Who is inside", inside.el) : null);
    if (ctx.isStaff) {
      replace(
        processBox,
        section(
          "Closing time",
          h("p", { class: "hint" }, "Ends the visits of branches that are closed, expires cards and unused passes of past days."),
          button("Process", () =>
            ctx.act(
              () => post("/access/process"),
              (r) => `Visits closed: ${r.visits_closed}. Cards expired: ${r.cards_expired}. Passes expired: ${r.passes_expired}.`,
              reloadAll,
            ),
          ),
        ),
      );
    }
    replace(ctx.body, section("Choose a branch", node), section("Occupancy", facts), insideBox, settingsBox, processBox);
    if (current()) await node.requestSubmit();
  },
};

// ---- LIB-UI-ACC-04 ---------------------------------------------------------------

const PASS_STATUSES = ["unused", "used", "cancelled"];

const dayPassesScreen = {
  id: "acc-04",
  title: "Day passes",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const map = await branchMap(ctx);
    const slip = h("div", { class: "pass-slip-box" });
    const resultBox = h("div", { class: "pass-result" });

    function showSlip(p) {
      replace(
        slip,
        h(
          "section",
          { class: "pass-slip", "aria-label": "Day pass" },
          h("h2", {}, "Day pass"),
          h("p", { class: "pass-code" }, p.code),
          definitionList([
            ["Visitor", p.visitor_name],
            ["Branch", branchName(map, p.branch_id)],
            ["Valid on", fmtDate(p.valid_on)],
            ["Price", fmtAmount(p.price)],
          ]),
        ),
      );
      slip.scrollIntoView?.({ block: "nearest" });
      setTimeout(() => {
        try {
          window.print();
        } catch {
          // printing is not available; the pass stays on the page
        }
      }, 50);
    }

    // sell
    const sellBranch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { activeOnly: true }) });
    const visitor = field({ name: "visitor_name", label: "Visitor name", attrs: { maxlength: "200" } });
    const sell = form({
      fields: [sellBranch, visitor],
      submit: "Sell",
      label: "Sell a day pass",
      async onSubmit(v) {
        sell.fieldErrors({});
        let problem = needBranch(v.branch_id);
        if (!problem && !v.visitor_name.trim()) {
          problem = clientError("VALIDATION_ERROR", "Enter the name of the visitor.", { fields: [{ field: "visitor_name", problem: "field required" }] });
        }
        if (problem) {
          ctx.fail(problem);
          sell.fieldErrors(fieldProblems(problem));
          return;
        }
        const p = await ctx.act(
          () => post("/day-passes", { branch_id: int(v.branch_id), visitor_name: v.visitor_name.trim() }),
          (x) => `Day pass ${x.code} sold for ${fmtAmount(x.price)}.`,
          () => list.reload(),
          (error) => sell.fieldErrors(fieldProblems(error)),
        );
        if (p) {
          visitor.input.value = "";
          replace(
            resultBox,
            definitionList([
              ["Code", p.code],
              ["Visitor", p.visitor_name],
              ["Valid on", fmtDate(p.valid_on)],
              ["Price", fmtAmount(p.price)],
            ]),
            button("Print", () => showSlip(p)),
          );
        }
      },
    });

    // list
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "All branches" }), value: branches.length ? branches[0].id : "" });
    const validOn = field({ name: "valid_on", label: "Valid on", type: "date", value: ctx.today });
    const status = field({ name: "status", label: "Status", options: choices(PASS_STATUSES, { any: "Any" }) });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Code", value: (p) => p.code },
        { label: "Branch", value: (p) => branchName(map, p.branch_id) },
        { label: "Visitor", value: (p) => p.visitor_name },
        { label: "Valid on", value: (p) => fmtDate(p.valid_on) },
        { label: "Price", value: (p) => fmtAmount(p.price) },
        { label: "Status", value: (p) => p.status },
        { label: "Sold at", value: (p) => fmtDateTime(p.sold_at) },
        {
          label: "Actions",
          value: (p) =>
            h(
              "span",
              { class: "row-actions" },
              button("Print", () => showSlip(p)),
              p.status === "unused"
                ? button("Cancel", () =>
                    ctx.ask({
                      text: `Cancel day pass ${p.code}?`,
                      onConfirm: () => ctx.act(() => post(`/day-passes/${p.id}/cancel`), `Day pass ${p.code} cancelled.`, () => list.reload()),
                    }),
                  )
                : null,
            ),
        },
      ],
      load: (page) =>
        get("/day-passes", { page, page_size: 20, branch_id: branch.input.value, valid_on: validOn.input.value, status: status.input.value }),
    });
    const filters = form({
      fields: [branch, validOn, status],
      submit: "Show",
      label: "Day pass filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    replace(ctx.body, section("Sell a day pass", sell, resultBox), slip, section("Day passes", filters, list.el));
    await list.goTo(1);
  },
};

// ---- LIB-UI-ACC-05 ---------------------------------------------------------------

const bansScreen = {
  id: "acc-05",
  title: "Bans and alerts",
  module: MODULE,
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const map = await branchMap(ctx);
    const member = await paramMember(ctx);
    const picker = memberPicker(ctx, {
      submit: "Open",
      value: member ? member.member_no : "",
      onPick: (m) => ctx.navigate(`#/acc-05/${m.id}`),
    });

    const alerts = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "Card number", value: (a) => a.card_no },
        { label: "Branch", value: (a) => branchName(map, a.branch_id) },
        { label: "At", value: (a) => fmtDateTime(a.at) },
      ],
      load: (page) => get("/access/alerts", { page, page_size: 20 }),
    });
    const alertsSection = section("Lost-card alerts", alerts.el);

    if (!member) {
      replace(ctx.body, section("Choose a member", picker), alertsSection);
      await alerts.goTo(1);
      return;
    }

    const id = member.id;
    const bans = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: [
        { label: "From", value: (b) => fmtDate(b.starts_on) },
        { label: "Until", value: (b) => fmtDate(b.ends_on) },
        { label: "Reason", value: (b) => b.reason },
        { label: "In force", value: (b) => fmtBool(b.in_force) },
        { label: "Lifted at", value: (b) => fmtDateTime(b.lifted_at) },
        {
          label: "Actions",
          value: (b) =>
            b.lifted_at
              ? "–"
              : button("Lift", () =>
                  ctx.ask({
                    text: `Lift the ban from ${fmtDate(b.starts_on)} to ${fmtDate(b.ends_on)}?`,
                    onConfirm: () => ctx.act(() => post(`/access-bans/${b.id}/lift`), "Ban lifted.", () => bans.reload()),
                  }),
                ),
        },
      ],
      load: (page) => get(`/members/${id}/access-bans`, { page, page_size: 10 }),
    });

    const reason = field({ name: "reason", label: "Reason", attrs: { maxlength: "200" } });
    const starts = field({ name: "starts_on", label: "Starts on", type: "date", value: ctx.today });
    const ends = field({ name: "ends_on", label: "Ends on", type: "date" });
    const create = form({
      fields: [reason, starts, ends],
      submit: "Create",
      label: "Create a ban",
      async onSubmit(v) {
        create.fieldErrors({});
        const done = await ctx.act(
          () => post(`/members/${id}/access-bans`, omitNull({ reason: v.reason.trim(), starts_on: text(v.starts_on), ends_on: text(v.ends_on) })),
          (b) => `Ban created until ${fmtDate(b.ends_on)}.`,
          () => bans.reload(),
          (error) => create.fieldErrors(fieldProblems(error)),
        );
        if (done) {
          reason.input.value = "";
          ends.input.value = "";
        }
      },
    });

    replace(
      ctx.body,
      section("Choose a member", picker),
      memberLine(member),
      section("Create a ban", create),
      section("Bans", bans.el),
      alertsSection,
    );
    await Promise.all([bans.goTo(1), alerts.goTo(1)]);
  },
};

// ---- LIB-UI-ACC-06 ---------------------------------------------------------------

const monthStart = (today) => `${today.slice(0, 8)}01`;

const visitsScreen = {
  id: "acc-06",
  title: "Visits report",
  module: MODULE,
  roles: ["all"],
  async render(ctx) {
    const branches = await ctx.branches();
    const map = await branchMap(ctx);
    const from = field({ name: "from", label: "From", type: "date", value: monthStart(ctx.today) });
    const to = field({ name: "to", label: "To", type: "date", value: ctx.today });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "All branches" }) });

    let list;
    if (ctx.isStaff) {
      list = pagedTable({
        onError: (e) => ctx.fail(e),
        columns: [
          { label: "Branch", value: (r) => branchName(map, r.branch_id) },
          { label: "Visits", value: (r) => String(r.visits) },
          { label: "Member visits", value: (r) => String(r.member_visits) },
          { label: "Unique members", value: (r) => String(r.unique_members) },
          { label: "Pass visits", value: (r) => String(r.pass_visits) },
          { label: "Average minutes", value: (r) => fmtText(r.average_minutes) },
          { label: "Peak occupancy", value: (r) => String(r.peak_occupancy) },
          { label: "Pass revenue", value: (r) => fmtAmount(r.pass_revenue) },
          { label: "Denied", value: (r) => String(r.denied) },
        ],
        load: (page) => get("/reports/visits", { page, page_size: 50, from: from.input.value, to: to.input.value, branch_id: branch.input.value }),
      });
    } else {
      const me = await get("/members/me");
      list = pagedTable({
        onError: (e) => ctx.fail(e),
        columns: [
          { label: "Branch", value: (v) => branchName(map, v.branch_id) },
          { label: "Entered at", value: (v) => fmtDateTime(v.entered_at) },
          { label: "Left at", value: (v) => fmtDateTime(v.left_at) },
          { label: "Minutes", value: (v) => fmtText(v.minutes) },
          { label: "Closed by", value: (v) => (v.closed_by ? words(v.closed_by) : "–") },
        ],
        load: (page) => get(`/members/${me.id}/visits`, { page, page_size: 20, from: from.input.value, to: to.input.value, branch_id: branch.input.value }),
      });
      from.input.value = "";
      to.input.value = "";
    }

    const node = form({
      fields: [from, to, branch],
      submit: "Show",
      label: ctx.isStaff ? "Visits report" : "My visits",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    replace(ctx.body, section(ctx.isStaff ? "Visits per branch" : "My visits", node, list.el));
    await list.goTo(1);
  },
};

export const accessScreens = [cardsScreen, gateScreen, occupancyScreen, dayPassesScreen, bansScreen, visitsScreen];
