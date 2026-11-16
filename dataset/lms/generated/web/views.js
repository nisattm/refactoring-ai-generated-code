// Table columns and loaders shared by several screens (loans, reservations, fees, notifications).

import { findMember } from "./context.js";
import {
  field,
  form,
  fmtAmount,
  fmtBool,
  fmtDate,
  fmtDateTime,
  fmtText,
  h,
  link,
  words,
} from "./ui.js";

export async function branchMap(ctx) {
  const map = new Map();
  for (const b of await ctx.branches()) map.set(b.id, b);
  return map;
}

export const branchName = (map, id) => (id === null || id === undefined ? "–" : map.get(id)?.name || `#${id}`);

/** Adds `_copy` and `_book` to loan-like items that carry `copy_id`. */
export async function withCopies(ctx, items) {
  await Promise.all(
    items.map(async (item) => {
      item._copy = await ctx.copy(item.copy_id);
      item._book = await ctx.book(item._copy.book_id);
    }),
  );
  return items;
}

export async function withBooks(ctx, items) {
  await Promise.all(
    items.map(async (item) => {
      item._book = await ctx.book(item.book_id);
    }),
  );
  return items;
}

export async function withMembers(ctx, items) {
  await Promise.all(
    items.map(async (item) => {
      item._member = await ctx.member(item.member_id);
    }),
  );
  return items;
}

export const bookLink = (book) => link(book.title, `#/cat-02/${book.id}`);
export const memberLink = (member) => link(member.member_no, `#/mem-03/${member.id}`);

/** Loans of a member or of everybody; `actions(loan)` adds a column of buttons. */
export function loanColumns({ withMember = false, actions } = {}) {
  const columns = [{ label: "ID", value: (l) => String(l.id) }];
  if (withMember) columns.push({ label: "Member", value: (l) => (l._member ? memberLink(l._member) : `#${l.member_id}`) });
  columns.push(
    { label: "Title", value: (l) => bookLink(l._book) },
    { label: "Barcode", value: (l) => l._copy.barcode },
    { label: "Loan date", value: (l) => fmtDate(l.loan_date) },
    { label: "Due date", value: (l) => fmtDate(l.due_date) },
    { label: "Status", value: (l) => l.status },
    { label: "Overdue", value: (l) => fmtBool(l.is_overdue) },
    { label: "Renewals", value: (l) => `${l.renewal_count} of ${l.max_renewals}` },
    { label: "Late fee", value: (l) => fmtAmount(l.accrued_late_fee) },
    { label: "Returned on", value: (l) => fmtDate(l.returned_on) },
  );
  if (actions) columns.push({ label: "Actions", value: (l) => actions(l) });
  return columns;
}

export function reservationColumns(map, { withMember = false, actions } = {}) {
  const columns = [{ label: "ID", value: (r) => String(r.id) }];
  if (withMember) columns.push({ label: "Member", value: (r) => (r._member ? memberLink(r._member) : `#${r.member_id}`) });
  columns.push(
    { label: "Title", value: (r) => bookLink(r._book) },
    { label: "Pickup branch", value: (r) => branchName(map, r.pickup_branch_id) },
    { label: "Status", value: (r) => r.status },
    { label: "Queue position", value: (r) => (r.queue_position === null ? "–" : String(r.queue_position)) },
    { label: "Hold until", value: (r) => fmtDate(r.hold_until) },
    { label: "Created", value: (r) => fmtDateTime(r.created_at) },
  );
  if (actions) columns.push({ label: "Actions", value: (r) => actions(r) });
  return columns;
}

export const ACTIVE_RESERVATION = new Set(["waiting", "in_transit", "ready"]);

export function feeColumns({ withMember = false, actions } = {}) {
  const columns = [{ label: "ID", value: (f) => String(f.id) }];
  if (withMember) columns.push({ label: "Member", value: (f) => (f._member ? memberLink(f._member) : `#${f.member_id}`) });
  columns.push(
    { label: "Kind", value: (f) => words(f.kind) },
    { label: "Amount", value: (f) => fmtAmount(f.amount) },
    { label: "Paid", value: (f) => fmtAmount(f.paid_amount) },
    { label: "Outstanding", value: (f) => fmtAmount(f.outstanding) },
    { label: "Status", value: (f) => f.status },
    { label: "Created", value: (f) => fmtDate(f.created_on) },
    { label: "Loan", value: (f) => fmtText(f.loan_id) },
  );
  if (actions) columns.push({ label: "Actions", value: (f) => actions(f) });
  return columns;
}

export function paymentColumns() {
  return [
    { label: "ID", value: (p) => String(p.id) },
    { label: "Paid at", value: (p) => fmtDateTime(p.paid_at) },
    { label: "Amount", value: (p) => fmtAmount(p.amount) },
    { label: "Method", value: (p) => p.method },
    {
      label: "Allocations",
      value: (p) => (p.allocations.length ? p.allocations.map((a) => `fee ${a.fee_id}: ${fmtAmount(a.amount)}`).join("; ") : "–"),
    },
  ];
}

export function notificationColumns({ withMember = false, actions } = {}) {
  const columns = [{ label: "Date", value: (n) => fmtDateTime(n.created_at) }];
  if (withMember) columns.push({ label: "Member", value: (n) => (n._member ? memberLink(n._member) : `#${n.member_id}`) });
  columns.push(
    { label: "Type", value: (n) => words(n.type) },
    { label: "Message", value: (n) => n.message },
    { label: "Read", value: (n) => (n.read_at ? fmtDateTime(n.read_at) : h("strong", { class: "unread-mark" }, "Unread")) },
  );
  if (actions) columns.push({ label: "Actions", value: (n) => actions(n) });
  return columns;
}

/** A field `member_no` and a button: finds the member and hands the record to onPick. */
export function memberPicker(ctx, { submit = "Open", onPick, value = "", label = "Member number" }) {
  const memberNo = field({ name: "member_no", label, value, hint: "For example M000001." });
  return form({
    fields: [memberNo],
    submit,
    label: "Choose a member",
    async onSubmit(v) {
      ctx.clearMessages();
      try {
        const member = await findMember(v.member_no);
        await onPick(member);
      } catch (error) {
        ctx.fail(error);
      }
    },
  });
}
