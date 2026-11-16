// Modules 5–8: loans, reservations, fees and payments, notifications.

import { get, post } from "../api.js";
import { clientError } from "../api.js";
import { findBook, findMember } from "../context.js";
import {
  BOOLEAN_FILTER,
  branchOptions,
  button,
  choices,
  definitionList,
  field,
  fmtAmount,
  fmtBool,
  fmtDate,
  form,
  h,
  pagedTable,
  replace,
  section,
  table,
  text,
  words,
} from "../ui.js";
import {
  ACTIVE_RESERVATION,
  branchMap,
  feeColumns,
  loanColumns,
  memberPicker,
  notificationColumns,
  paymentColumns,
  reservationColumns,
  withBooks,
  withCopies,
  withMembers,
} from "../views.js";

const LOAN_STATUSES = ["open", "returned", "lost"];
const RESERVATION_STATUSES = ["waiting", "in_transit", "ready", "fulfilled", "cancelled", "expired"];
const FEE_KINDS = [
  "late_fee",
  "damage_fee",
  "lost_book",
  "lost_processing",
  "no_show_fee",
  "equipment_late_fee",
  "equipment_damage_fee",
  "equipment_lost",
  "ill_request_fee",
  "ill_late_fee",
  "ill_lost",
  "event_fee",
  "reserve_late_fee",
  "reserve_lost",
  "card_replacement",
];
const NOTIFICATION_TYPES = [
  "reservation_ready", "reservation_in_transit", "reservation_expired", "reservation_cancelled",
  "loan_created", "loan_renewed", "loan_returned", "loan_lost", "fee_created", "payment_received", "fee_waived",
  "membership_renewed", "member_deactivated", "due_reminder", "overdue_notice",
  "room_booking_cancelled", "room_no_show", "room_ban_started", "room_participant_added", "room_reminder",
  "equipment_loan_created", "equipment_loan_returned", "equipment_loan_lost", "equipment_reservation_cancelled",
  "equipment_reservation_expired", "equipment_overdue",
  "digital_hold_ready", "digital_hold_expired", "digital_hold_cancelled", "digital_loan_expired", "digital_loan_due_soon",
  "ill_request_rejected", "ill_request_cancelled", "ill_request_received", "ill_request_uncollected", "ill_renewal_answered",
  "event_cancelled", "event_changed", "event_promoted", "event_reminder", "event_ban_started",
  "course_enrolled", "course_activated", "reserve_item_available", "reserve_overdue",
  "donation_reviewed", "donation_received", "donation_expired", "donor_level_reached",
  "suggestion_approved", "suggestion_rejected", "suggestion_ordered", "suggestion_available", "suggestion_expired",
  "program_completed", "program_level_reached", "program_cancelled", "program_ending",
  "announcement", "message_reply", "card_issued", "access_banned", "lost_card_used",
];

const CONDITIONS = [
  { value: "good", label: "Good" },
  { value: "damaged", label: "Damaged" },
];

// ---- returning (shared by LIB-UI-LOAN-01 and LIB-UI-LOAN-02) ----------------------

function returnFields(branches) {
  return {
    branch_id: field({ name: "branch_id", label: "Return branch", options: branchOptions(branches, { activeOnly: true }) }),
    condition: field({ name: "condition", label: "Condition", options: CONDITIONS }),
    damage_fee: field({ name: "damage_fee", label: "Damage fee", inputmode: "decimal", hint: "Required when damaged; at most the price of the copy." }),
  };
}

function returnBody(v) {
  const body = { branch_id: Number(v.branch_id), condition: v.condition };
  const fee = text(v.damage_fee);
  if (fee !== null) body.damage_fee = fee;
  return body;
}

async function returnSummary(ctx, loan) {
  const fees = await get("/fees", { loan_id: loan.id, page_size: 100 });
  const late = fees.items.filter((f) => f.kind === "late_fee").reduce((sum, f) => sum + Number(f.amount), 0);
  const damage = fees.items.filter((f) => f.kind === "damage_fee").reduce((sum, f) => sum + Number(f.amount), 0);
  return h(
    "div",
    { class: "return-result" },
    definitionList([
      ["Loan", String(loan.id)],
      ["Returned on", fmtDate(loan.returned_on)],
      ["Late days", String(loan.late_days ?? 0)],
      ["Late fee", fmtAmount(late.toFixed(2))],
      ["Damage fee", fmtAmount(damage.toFixed(2))],
    ]),
    fees.items.length ? table({ columns: feeColumns(), rows: fees.items }) : null,
  );
}

async function openLoanOfBarcode(barcode) {
  const wanted = String(barcode ?? "").trim();
  if (!wanted) throw clientError("VALIDATION_ERROR", "Enter a barcode.", { fields: [{ field: "barcode", problem: "field required" }] });
  const copy = await get(`/copies/by-barcode/${encodeURIComponent(wanted)}`);
  const loans = await get("/loans", { copy_id: copy.id, status: "open", page_size: 1 });
  if (!loans.items.length) throw clientError("LOAN_NOT_OPEN", `Copy ${copy.barcode} has no open loan.`, { barcode: copy.barcode });
  return loans.items[0];
}

// ---- LIB-UI-LOAN-01 --------------------------------------------------------------

const loanDeskScreen = {
  id: "loan-01",
  title: "Loan desk",
  module: "Loans and returns",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const lendResult = h("div", { class: "lend-result" });
    const returnResult = h("div", { class: "return-box" });

    const memberNo = field({ name: "member_no", label: "Member number", hint: "For example M000001." });
    const barcode = field({ name: "barcode", label: "Barcode" });
    const lend = form({
      fields: [memberNo, barcode],
      submit: "Lend",
      label: "Lend",
      async onSubmit(v) {
        replace(lendResult);
        const loan = await ctx.act(
          async () => {
            const member = await findMember(v.member_no);
            return post("/loans", { member_id: member.id, barcode: v.barcode.trim() });
          },
          (l) => `Loan created. Due date: ${fmtDate(l.due_date)}`,
        );
        if (loan) {
          await withCopies(ctx, [loan]);
          replace(
            lendResult,
            definitionList([
              ["Title", loan._book.title],
              ["Barcode", loan._copy.barcode],
              ["Due date", fmtDate(loan.due_date)],
            ]),
          );
          barcode.input.value = "";
        }
      },
    });

    const rBarcode = field({ name: "barcode", label: "Barcode" });
    const rf = returnFields(branches);
    const ret = form({
      fields: [rBarcode, ...Object.values(rf)],
      submit: "Return",
      label: "Return",
      async onSubmit(v) {
        replace(returnResult);
        const loan = await ctx.act(
          async () => {
            const open = await openLoanOfBarcode(v.barcode);
            return post(`/loans/${open.id}/return`, returnBody(v));
          },
          (l) => `Returned. Late days: ${l.late_days ?? 0}. Late fee: ${fmtAmount(l.accrued_late_fee)}`,
        );
        if (loan) {
          try {
            replace(returnResult, await returnSummary(ctx, loan));
          } catch (error) {
            ctx.fail(error);
          }
          rBarcode.input.value = "";
          rf.damage_fee.input.value = "";
        }
      },
    });
    replace(ctx.body, section("Lend a copy", lend, lendResult), section("Return a copy", ret, returnResult));
  },
};

// ---- LIB-UI-LOAN-02 --------------------------------------------------------------

const loansScreen = {
  id: "loan-02",
  title: "Loans",
  module: "Loans and returns",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const memberNo = field({ name: "member_no", label: "Member number" });
    const barcode = field({ name: "barcode", label: "Barcode" });
    const isbn = field({ name: "isbn", label: "ISBN" });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches, { any: "Any" }) });
    const status = field({ name: "status", label: "Status", options: choices(LOAN_STATUSES, { any: "Any" }) });
    const overdue = field({ name: "overdue", label: "Overdue", options: BOOLEAN_FILTER });
    const dueBefore = field({ name: "due_before", label: "Due on or before", type: "date" });
    const panel = h("div", { class: "return-panel" });
    let returning = null;

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: loanColumns({
        withMember: true,
        actions: (loan) =>
          loan.status !== "open"
            ? "–"
            : h(
                "span",
                { class: "row-actions" },
                button("Renew", () => ctx.act(() => post(`/loans/${loan.id}/renew`), (l) => `Loan renewed. New due date: ${fmtDate(l.due_date)}`, () => list.reload())),
                returning ? null : button("Return", () => openReturn(loan)),
                button("Report lost", () => ctx.act(() => post(`/loans/${loan.id}/report-lost`), "Loan reported lost.", () => list.reload())),
              ),
      }),
      load: async (page) => {
        const query = { page, page_size: 20, branch_id: branch.input.value, status: status.input.value, overdue: overdue.input.value, due_before: dueBefore.input.value };
        if (memberNo.input.value.trim()) query.member_id = (await findMember(memberNo.input.value)).id;
        if (barcode.input.value.trim()) query.copy_id = (await get(`/copies/by-barcode/${encodeURIComponent(barcode.input.value.trim())}`)).id;
        if (isbn.input.value.trim()) query.book_id = (await findBook(isbn.input.value)).id;
        const data = await get("/loans", query);
        await Promise.all([withCopies(ctx, data.items), withMembers(ctx, data.items)]);
        return data;
      },
    });

    function openReturn(loan) {
      returning = loan;
      const rf = returnFields(branches);
      const node = form({
        fields: Object.values(rf),
        submit: "Return",
        label: "Return a loan",
        extra: button("Back", closeReturn),
        async onSubmit(v) {
          const done = await ctx.act(
            () => post(`/loans/${loan.id}/return`, returnBody(v)),
            (l) => `Returned. Late days: ${l.late_days ?? 0}. Late fee: ${fmtAmount(l.accrued_late_fee)}`,
            async (l) => {
              replace(panel, section("Return result", await returnSummary(ctx, l)));
              returning = null;
              await list.reload();
            },
          );
          return done;
        },
      });
      replace(panel, section(`Return loan ${loan.id}: ${loan._book.title}`, node));
      list.reload();
    }
    function closeReturn() {
      returning = null;
      replace(panel);
      list.reload();
    }

    const filters = form({
      fields: [memberNo, barcode, isbn, branch, status, overdue, dueBefore],
      submit: "Filter",
      label: "Loan filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    replace(ctx.body, filters, panel, list.el);
    await list.goTo(1);
  },
};

// ---- LIB-UI-LOAN-03 --------------------------------------------------------------

const myLoansScreen = {
  id: "loan-03",
  title: "My loans",
  module: "Loans and returns",
  roles: ["member"],
  async render(ctx) {
    const me = await get("/members/me");
    const status = field({ name: "status", label: "Status", options: choices(LOAN_STATUSES, { any: "Any" }) });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: loanColumns({
        actions: (loan) =>
          loan.status === "open"
            ? button("Renew", () => ctx.act(() => post(`/loans/${loan.id}/renew`), (l) => `Loan renewed. New due date: ${fmtDate(l.due_date)}`, () => list.reload()))
            : "–",
      }),
      load: async (page) => {
        const data = await get(`/members/${me.id}/loans`, { page, page_size: 20, status: status.input.value });
        await withCopies(ctx, data.items);
        return data;
      },
    });
    const filters = form({
      fields: [status],
      submit: "Filter",
      label: "Loan filters",
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

// ---- LIB-UI-RES-01 ---------------------------------------------------------------

function cancelButton(ctx, reservation, reload) {
  return ACTIVE_RESERVATION.has(reservation.status)
    ? button("Cancel", () =>
        ctx.ask({
          text: `Cancel the reservation of “${reservation._book.title}”?`,
          onConfirm: () => ctx.act(() => post(`/reservations/${reservation.id}/cancel`), "Reservation cancelled.", reload),
        }),
      )
    : "–";
}

const myReservationsScreen = {
  id: "res-01",
  title: "My reservations",
  module: "Reservations",
  roles: ["member"],
  async render(ctx) {
    const me = await get("/members/me");
    const map = await branchMap(ctx);
    const status = field({ name: "status", label: "Status", options: choices(RESERVATION_STATUSES, { any: "Any" }) });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: reservationColumns(map, { actions: (r) => cancelButton(ctx, r, () => list.reload()) }),
      load: async (page) => {
        const data = await get(`/members/${me.id}/reservations`, { page, page_size: 20, status: status.input.value });
        await withBooks(ctx, data.items);
        return data;
      },
    });
    const filters = form({
      fields: [status],
      submit: "Filter",
      label: "Reservation filters",
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

// ---- LIB-UI-RES-02 ---------------------------------------------------------------

const reservationsScreen = {
  id: "res-02",
  title: "Reservations",
  module: "Reservations",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const branches = await ctx.branches();
    const map = await branchMap(ctx);

    const fMember = field({ name: "member_no", label: "Member number" });
    const fIsbn = field({ name: "isbn", label: "ISBN" });
    const fBranch = field({ name: "pickup_branch_id", label: "Pickup branch", options: branchOptions(branches, { any: "Any" }) });
    const fStatus = field({ name: "status", label: "Status", options: choices(RESERVATION_STATUSES, { any: "Any" }) });
    const queueBox = h("div", { class: "queue-box" });

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: reservationColumns(map, { withMember: true, actions: (r) => cancelButton(ctx, r, reloadAll) }),
      load: async (page) => {
        const query = { page, page_size: 20, pickup_branch_id: fBranch.input.value, status: fStatus.input.value };
        if (fMember.input.value.trim()) query.member_id = (await findMember(fMember.input.value)).id;
        if (fIsbn.input.value.trim()) query.book_id = (await findBook(fIsbn.input.value)).id;
        const data = await get("/reservations", query);
        await Promise.all([withBooks(ctx, data.items), withMembers(ctx, data.items)]);
        return data;
      },
    });

    async function showQueue() {
      ctx.clearMessages();
      try {
        const book = await findBook(fIsbn.input.value);
        const queue = pagedTable({
          onError: (e) => ctx.fail(e),
          columns: reservationColumns(map, { withMember: true, actions: (r) => cancelButton(ctx, r, reloadAll) }),
          load: async (page) => {
            const data = await get(`/books/${book.id}/reservations`, { page, page_size: 20 });
            await Promise.all([withBooks(ctx, data.items), withMembers(ctx, data.items)]);
            return data;
          },
        });
        showQueue.current = queue;
        replace(queueBox, section(`Queue of ${book.title}`, queue.el));
        await queue.goTo(1);
      } catch (error) {
        ctx.fail(error);
      }
    }
    const reloadAll = () => Promise.all([list.reload(), showQueue.current?.reload()]);

    const filters = form({
      fields: [fMember, fIsbn, fBranch, fStatus],
      submit: "Filter",
      label: "Reservation filters",
      cls: "filters",
      extra: button("Show queue", showQueue),
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });

    const cMember = field({ name: "member_no", label: "Member number" });
    const cIsbn = field({ name: "isbn", label: "ISBN" });
    const cBranch = field({ name: "pickup_branch_id", label: "Pickup branch", options: branchOptions(branches, { activeOnly: true }) });
    const create = form({
      fields: [cMember, cIsbn, cBranch],
      submit: "Reserve",
      label: "Reserve for a member",
      async onSubmit(v) {
        await ctx.act(
          async () => {
            const member = await findMember(v.member_no);
            const book = await findBook(v.isbn);
            return post("/reservations", { member_id: member.id, book_id: book.id, pickup_branch_id: Number(v.pickup_branch_id) });
          },
          (r) => `Reservation created. Queue position: ${r.queue_position ?? "–"}`,
          reloadAll,
        );
      },
    });

    const process = button("Process expired", () =>
      ctx.act(() => post("/reservations/process-expired"), (r) => `Expired reservations processed: ${r.expired}`, reloadAll),
    );
    replace(
      ctx.body,
      section("New reservation", create),
      h("div", { class: "actions" }, process),
      section("Reservation list", filters, list.el),
      queueBox,
    );
    await list.goTo(1);
  },
};

// ---- fees ------------------------------------------------------------------------

function balanceFacts(balance) {
  return definitionList([
    ["Outstanding fees", fmtAmount(balance.outstanding_fees)],
    ["Accrued late fees", fmtAmount(balance.accrued_late_fees)],
    ["Total debt", fmtAmount(balance.total_debt)],
    ["Blocked", fmtBool(balance.blocked)],
  ]);
}

// ---- LIB-UI-FEE-01 ---------------------------------------------------------------

const myFeesScreen = {
  id: "fee-01",
  title: "My fees",
  module: "Fines and payments",
  roles: ["member"],
  async render(ctx) {
    const me = await get("/members/me");
    const balanceBox = h("div", { class: "balance" });
    const fees = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: feeColumns(),
      load: (page) => get(`/members/${me.id}/fees`, { page, page_size: 20 }),
    });
    const payments = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: paymentColumns(),
      load: (page) => get(`/members/${me.id}/payments`, { page, page_size: 20 }),
    });
    replace(ctx.body, section("Balance", balanceBox), section("Fees", fees.el), section("Payments", payments.el));
    replace(balanceBox, balanceFacts(await get(`/members/${me.id}/balance`)));
    await Promise.all([fees.goTo(1), payments.goTo(1)]);
  },
};

// ---- LIB-UI-FEE-02 ---------------------------------------------------------------

const feesScreen = {
  id: "fee-02",
  title: "Fees and payments",
  module: "Fines and payments",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    let member = null;
    if (/^\d+$/.test(ctx.param)) member = await get(`/members/${ctx.param}`);
    const memberNo = field({ name: "member_no", label: "Member number", value: member?.member_no, hint: "Leave empty to list the fees of all members." });
    const status = field({ name: "status", label: "Status", options: choices(["open", "paid", "waived"], { any: "Any" }) });
    const kind = field({ name: "kind", label: "Kind", options: choices(FEE_KINDS, { any: "Any" }) });
    const account = h("div", { class: "member-account" });
    const paymentResult = h("div", { class: "payment-result" });

    const feeActions = (fee) => {
      if (!ctx.isAdmin || fee.status !== "open") return "–";
      const reason = field({ name: "reason", label: "Reason", hint: "5–500 characters." });
      const wrap = h("form", { class: "inline-waive", novalidate: true }, reason, h("button", { type: "submit" }, "Waive"));
      wrap.addEventListener("submit", (event) => {
        event.preventDefault();
        ctx.act(() => post(`/fees/${fee.id}/waive`, { reason: reason.input.value.trim() }), `Fee ${fee.id} waived.`, reloadAll);
      });
      return wrap;
    };

    const fees = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: feeColumns({ withMember: true, actions: feeActions }),
      load: async (page) => {
        const query = { page, page_size: 20, status: status.input.value, kind: kind.input.value };
        if (member) query.member_id = member.id;
        const data = await get("/fees", query);
        await withMembers(ctx, data.items);
        return data;
      },
    });
    const payments = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: paymentColumns(),
      load: (page) => get(`/members/${member.id}/payments`, { page, page_size: 20 }),
    });

    async function loadAccount() {
      if (!member) {
        replace(account);
        return;
      }
      const balance = await get(`/members/${member.id}/balance`);
      const amount = field({ name: "amount", label: "Amount", inputmode: "decimal", hint: "At most the outstanding fees." });
      const method = field({ name: "method", label: "Method", options: choices(["cash", "card"]) });
      const pay = form({
        fields: [amount, method],
        submit: "Pay",
        label: "Record a payment",
        async onSubmit(v) {
          replace(paymentResult);
          const payment = await ctx.act(
            () => post(`/members/${member.id}/payments`, { amount: v.amount.trim(), method: v.method }),
            (p) => `Payment of ${fmtAmount(p.amount)} recorded.`,
            reloadAll,
          );
          if (payment) {
            replace(
              paymentResult,
              section(
                "Allocations",
                table({
                  columns: [
                    { label: "Fee", value: (a) => String(a.fee_id) },
                    { label: "Amount", value: (a) => fmtAmount(a.amount) },
                  ],
                  rows: payment.allocations,
                }),
              ),
            );
          }
        },
      });
      replace(
        account,
        section(`Account of ${member.full_name} (${member.member_no})`, balanceFacts(balance)),
        section("Record a payment", pay, paymentResult),
        section("Payments", payments.el),
      );
      await payments.goTo(1);
    }
    const reloadAll = async () => {
      await Promise.all([loadAccount(), fees.reload()]);
    };

    const filters = form({
      fields: [memberNo, status, kind],
      submit: "Show",
      label: "Fee filters",
      cls: "filters",
      async onSubmit(v) {
        ctx.clearMessages();
        replace(paymentResult);
        try {
          member = v.member_no.trim() ? await findMember(v.member_no) : null;
          await Promise.all([loadAccount(), fees.goTo(1)]);
        } catch (error) {
          ctx.fail(error);
        }
      },
    });
    replace(ctx.body, filters, account, section("Fees", fees.el));
    await Promise.all([loadAccount(), fees.goTo(1)]);
  },
};

// ---- LIB-UI-NOT-01 ---------------------------------------------------------------

const myNotificationsScreen = {
  id: "not-01",
  title: "My notifications",
  module: "Notifications",
  roles: ["member"],
  async render(ctx) {
    const me = await get("/members/me");
    const unread = field({ name: "unread", label: "Unread", options: BOOLEAN_FILTER });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: notificationColumns({
        actions: (n) =>
          n.read_at ? "–" : button("Mark as read", () => ctx.act(() => post(`/notifications/${n.id}/read`), "Notification marked as read.", () => list.reload())),
      }),
      load: (page) => get(`/members/${me.id}/notifications`, { page, page_size: 20, unread: unread.input.value }),
      rowClass: (n) => (n.read_at ? "" : "unread"),
    });
    const filters = form({
      fields: [unread],
      submit: "Filter",
      label: "Notification filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    replace(
      ctx.body,
      h(
        "div",
        { class: "actions" },
        button("Mark all as read", () =>
          ctx.act(() => post(`/members/${me.id}/notifications/read-all`), (r) => `Notifications marked as read: ${r.updated}`, () => list.reload()),
        ),
      ),
      filters,
      list.el,
    );
    await list.goTo(1);
  },
};

// ---- LIB-UI-NOT-02 ---------------------------------------------------------------

const notificationsScreen = {
  id: "not-02",
  title: "Notifications",
  module: "Notifications",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const memberNo = field({ name: "member_no", label: "Member number" });
    const unread = field({ name: "unread", label: "Unread", options: BOOLEAN_FILTER });
    const type = field({ name: "type", label: "Type", options: choices(NOTIFICATION_TYPES, { any: "Any" }) });
    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: notificationColumns({ withMember: true }),
      rowClass: (n) => (n.read_at ? "" : "unread"),
      load: async (page) => {
        const query = { page, page_size: 20, unread: unread.input.value, type: type.input.value };
        if (memberNo.input.value.trim()) query.member_id = (await findMember(memberNo.input.value)).id;
        const data = await get("/notifications", query);
        await withMembers(ctx, data.items);
        return data;
      },
    });
    const filters = form({
      fields: [memberNo, unread, type],
      submit: "Filter",
      label: "Notification filters",
      cls: "filters",
      onSubmit() {
        ctx.clearMessages();
        list.goTo(1);
      },
    });
    replace(
      ctx.body,
      h(
        "div",
        { class: "actions" },
        button("Run reminders", () =>
          ctx.act(
            () => post("/notifications/run-reminders"),
            (r) => `Reminders created: ${r.due_reminders} due reminders, ${r.overdue_notices} overdue notices.`,
            () => list.reload(),
          ),
        ),
      ),
      filters,
      list.el,
    );
    await list.goTo(1);
  },
};

export const circulationScreens = [
  loanDeskScreen,
  loansScreen,
  myLoansScreen,
  myReservationsScreen,
  reservationsScreen,
  myFeesScreen,
  feesScreen,
  myNotificationsScreen,
  notificationsScreen,
];
