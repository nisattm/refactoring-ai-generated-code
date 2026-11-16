// Module 22: donations (donors, offer form, review, receiving desk, receipts, donor wall and reports).
// Module: Donations.

import { clientError, fetchAll, get, patch, post } from "../api.js";
import { findMember } from "../context.js";
import {
  BOOLEAN_FILTER,
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
  guarded,
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
  words,
} from "../ui.js";
import { branchMap, branchName } from "../views.js";

const DONOR_KINDS = ["person", "organization"];
const LEVELS = ["none", "bronze", "silver", "gold"];
const CONDITIONS = ["new", "good", "fair", "poor"];
const DECLINE_REASONS = ["duplicate", "poor_condition", "out_of_scope", "too_old", "other"];
const DONATION_STATUSES = ["offered", "accepted", "rejected", "partially_received", "received", "expired", "cancelled"];
const OPEN_STATUSES = ["offered", "accepted", "partially_received"];
const MAX_ITEMS = 30;

// ---- helpers ---------------------------------------------------------------------

/** Donor records are read once per screen; GET /donors/{id} is for librarians and admins. */
function donorDirectory() {
  const cache = new Map();
  const find = (id) => {
    if (!cache.has(id)) cache.set(id, get(`/donors/${id}`).catch(() => null));
    return cache.get(id);
  };
  return {
    find,
    async name(id) {
      const donor = await find(id);
      return donor ? donor.name : `#${id}`;
    },
    async annotate(donations) {
      await Promise.all(
        donations.map(async (d) => {
          d._donorName = await this.name(d.donor_id);
        }),
      );
      return donations;
    },
  };
}

/** field name → problem text, from a 422 answer or from `details.field` of a 409 answer. */
function problems(error, rename = {}) {
  const out = fieldProblems(error);
  const single = error?.details?.field;
  if (typeof single === "string" && !out[single]) out[single] = error.message;
  for (const [from, to] of Object.entries(rename)) {
    if (out[from]) {
      out[to] = out[from];
      delete out[from];
    }
  }
  return out;
}

const donorLink = (id, name) => link(name ?? `#${id}`, `#/don-01/${id}`);

const itemsText = (d) => d.items.map((i) => `${i.title} × ${i.quantity}`).join("; ");

function receiptLink(d) {
  return d.receipt_no ? link(d.receipt_no, `#/don-05/${d.id}`) : "–";
}

function donationColumns(map, { withDonor = false, actions } = {}) {
  const columns = [{ label: "ID", value: (d) => String(d.id) }];
  if (withDonor) columns.push({ label: "Donor", value: (d) => donorLink(d.donor_id, d._donorName) });
  columns.push(
    { label: "Branch", value: (d) => branchName(map, d.branch_id) },
    { label: "Status", value: (d) => d.status },
    { label: "Offered", value: (d) => fmtDate(d.offered_at) },
    { label: "Titles", value: (d) => itemsText(d) },
    { label: "Copies offered", value: (d) => String(d.copies_offered) },
    { label: "Expected by", value: (d) => fmtDate(d.expected_by) },
    { label: "Last received", value: (d) => fmtDate(d.received_at) },
    { label: "Receipt", value: (d) => receiptLink(d) },
  );
  if (actions) columns.push({ label: "Actions", value: (d) => actions(d) });
  return columns;
}

const levelText = (level) => words(level);

// ---- LIB-UI-DON-01 ---------------------------------------------------------------

async function donorPage(ctx, id) {
  const map = await branchMap(ctx);
  const dir = donorDirectory();
  const box = h("div", { class: "donor-page" });

  async function show() {
    const donor = await get(`/donors/${id}`);
    const history = await get(`/donors/${id}/history`);
    let mergedInto = null;
    if (donor.merged_into_id) mergedInto = await dir.find(donor.merged_into_id);
    let member = null;
    if (donor.member_id) member = await ctx.member(donor.member_id).catch(() => null);
    const merged = Boolean(donor.merged_into_id);

    const facts = section(
      `Donor ${donor.name}`,
      definitionList([
        ["Name", donor.name],
        ["Kind", words(donor.kind)],
        ["Email", fmtText(donor.email)],
        ["Phone", fmtText(donor.phone)],
        ["Member", member ? link(`${member.member_no} – ${member.full_name}`, `#/mem-03/${member.id}`) : donor.member_id ? `#${donor.member_id}` : "–"],
        ["Anonymous", fmtBool(donor.anonymous)],
        ["Active", fmtBool(donor.is_active)],
        ["Level this year", levelText(donor.level)],
        ["Value this year", fmtAmount(donor.value_this_year)],
        ["Merged into", donor.merged_into_id ? donorLink(donor.merged_into_id, mergedInto ? mergedInto.name : null) : "–"],
        ["Created", fmtDateTime(donor.created_at)],
      ]),
      merged
        ? h("p", {}, "This donor was merged into another donor and cannot be changed.")
        : h(
            "div",
            { class: "actions" },
            donor.is_active
              ? button("Deactivate", () =>
                  ctx.ask({
                    text: `Deactivate donor ${donor.name}? An inactive donor cannot get new offers.`,
                    onConfirm: () => ctx.act(() => patch(`/donors/${id}`, { is_active: false }), "Donor deactivated.", show),
                  }),
                )
              : button("Activate", () => ctx.act(() => patch(`/donors/${id}`, { is_active: true }), "Donor activated.", show)),
          ),
    );

    const parts = [h("p", {}, link("All donors", "#/don-01")), facts];

    if (!merged) {
      const name = field({ name: "name", label: "Name", value: donor.name, attrs: { maxlength: "200" } });
      const email = field({ name: "email", label: "Email", value: donor.email ?? "", type: "email" });
      const phone = field({ name: "phone", label: "Phone", value: donor.phone ?? "" });
      const anonymous = field({
        name: "anonymous",
        label: "Anonymous",
        options: [
          { value: "false", label: "No" },
          { value: "true", label: "Yes" },
        ],
        value: String(donor.anonymous),
        hint: "An anonymous donor is only counted on the donor wall.",
      });
      const fields = [name, email, phone, anonymous];
      const edit = h("form", { class: "form", novalidate: true, "data-form": "Edit donor" }, fields);
      edit.append(h("div", { class: "actions" }, h("button", { type: "submit" }, "Save")));
      edit.addEventListener(
        "submit",
        guarded(async (event) => {
          event.preventDefault();
          for (const f of fields) f.setError("");
          await ctx.act(
            () =>
              patch(`/donors/${id}`, {
                name: name.input.value.trim(),
                email: text(email.input.value),
                phone: text(phone.input.value),
                anonymous: anonymous.input.value === "true",
              }),
            "Donor saved.",
            show,
            (error) => {
              for (const [key, problem] of Object.entries(problems(error))) fields.find((f) => f.input.name === key)?.setError(problem);
            },
          );
        }),
      );
      parts.push(section("Change donor", edit));
    }

    if (ctx.isAdmin && !merged) {
      const others = (await fetchAll("/donors", { is_active: "true" })).filter((d) => d.id !== donor.id && !d.merged_into_id);
      const target = field({
        name: "into_donor_id",
        label: "Merge into",
        options: others.length ? recordOptions(others, (d) => `${d.name} (#${d.id})`) : [{ value: "", label: "No other donor" }],
      });
      const mergeForm = h("form", { class: "form", novalidate: true, "data-form": "Merge donors" }, target);
      mergeForm.append(h("div", { class: "actions" }, h("button", { type: "submit" }, "Merge")));
      mergeForm.addEventListener(
        "submit",
        guarded((event) => {
          event.preventDefault();
          const targetId = int(target.input.value);
          if (targetId === null) {
            ctx.fail(clientError("VALIDATION_ERROR", "Choose the donor to merge into.", { fields: [{ field: "into_donor_id", problem: "field required" }] }));
            return;
          }
          const label = target.input.selectedOptions[0]?.textContent ?? `#${targetId}`;
          ctx.ask({
            text: `Merge ${donor.name} into ${label}? All donations move to the target and ${donor.name} becomes inactive. This cannot be undone.`,
            onConfirm: () =>
              ctx.act(
                () => post(`/donors/${id}/merge`, { into_donor_id: targetId }),
                (t) => `Donor merged into ${t.name}.`,
                (t) => ctx.navigate(`#/don-01/${t.id}`),
              ),
          });
        }),
      );
      parts.push(section("Merge donor", h("p", { class: "hint" }, "Moves every donation of this donor to the chosen donor."), mergeForm));
    }

    parts.push(
      section(
        "History",
        definitionList([
          ["Donations", String(history.donations)],
          ["Open donations", String(history.open_donations)],
          ["Copies received", String(history.copies_received)],
          ["Value received", fmtAmount(history.value_received)],
          ["First received on", fmtDate(history.first_received_on)],
          ["Last received on", fmtDate(history.last_received_on)],
        ]),
        table({
          caption: "Value by year",
          columns: [
            { label: "Year", value: (y) => String(y.year) },
            { label: "Value", value: (y) => fmtAmount(y.value) },
            { label: "Level", value: (y) => levelText(y.level) },
          ],
          rows: history.years,
        }),
      ),
    );

    const donations = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: donationColumns(map, {
        actions: (d) =>
          h(
            "span",
            { class: "row-actions" },
            d.status === "offered" ? link("Review", `#/don-03/${d.id}`) : null,
            d.status === "accepted" || d.status === "partially_received" ? link("Receive", `#/don-04/${d.id}`) : null,
          ),
      }),
      load: (page) => get("/donations", { donor_id: id, page, page_size: 20 }),
    });
    parts.push(section("Donations", donations.el));
    replace(box, ...parts);
    await donations.goTo(1);
  }

  replace(ctx.body, box);
  await show();
}

async function donorList(ctx) {
  const q = field({ name: "q", label: "Name or email contains" });
  const kind = field({ name: "kind", label: "Kind", options: choices(DONOR_KINDS, { any: "Any" }) });
  const active = field({ name: "is_active", label: "Active", options: BOOLEAN_FILTER });
  const level = field({ name: "level", label: "Level (this year)", options: choices(LEVELS, { any: "Any" }) });
  const list = pagedTable({
    onError: (e) => ctx.fail(e),
    onRowClick: (d) => ctx.navigate(`#/don-01/${d.id}`),
    columns: [
      { label: "Name", value: (d) => donorLink(d.id, d.name) },
      { label: "Kind", value: (d) => words(d.kind) },
      { label: "Email", value: (d) => fmtText(d.email) },
      { label: "Phone", value: (d) => fmtText(d.phone) },
      { label: "Member", value: (d) => (d._member ? link(d._member.member_no, `#/mem-03/${d._member.id}`) : "–") },
      { label: "Anonymous", value: (d) => fmtBool(d.anonymous) },
      { label: "Active", value: (d) => fmtBool(d.is_active) },
      { label: "Level", value: (d) => levelText(d.level) },
      { label: "Value this year", value: (d) => fmtAmount(d.value_this_year) },
      { label: "Merged into", value: (d) => (d.merged_into_id ? donorLink(d.merged_into_id) : "–") },
    ],
    load: async (page) => {
      const data = await get("/donors", {
        page,
        page_size: 20,
        q: q.input.value.trim(),
        kind: kind.input.value,
        is_active: active.input.value,
        level: level.input.value,
      });
      await Promise.all(
        data.items.map(async (d) => {
          d._member = d.member_id ? await ctx.member(d.member_id).catch(() => null) : null;
        }),
      );
      return data;
    },
  });
  const filters = h("form", { class: "form filters", novalidate: true, "data-form": "Donor filters" }, q, kind, active, level);
  filters.append(h("div", { class: "actions" }, h("button", { type: "submit" }, "Filter")));
  filters.addEventListener(
    "submit",
    guarded((event) => {
      event.preventDefault();
      ctx.clearMessages();
      return list.goTo(1);
    }),
  );

  const cKind = field({ name: "kind", label: "Kind", options: choices(DONOR_KINDS), value: "person" });
  const cName = field({ name: "name", label: "Name", attrs: { maxlength: "200" } });
  const cEmail = field({ name: "email", label: "Email", type: "email" });
  const cPhone = field({ name: "phone", label: "Phone" });
  const cMember = field({ name: "member_no", label: "Member number", hint: "Optional. Links a person to a member, for example M000001." });
  const cAnonymous = field({
    name: "anonymous",
    label: "Anonymous",
    options: [
      { value: "false", label: "No" },
      { value: "true", label: "Yes" },
    ],
  });
  const cFields = [cKind, cName, cEmail, cPhone, cMember, cAnonymous];
  const create = h("form", { class: "form", novalidate: true, "data-form": "Create donor" }, cFields);
  create.append(h("div", { class: "actions" }, h("button", { type: "submit" }, "Create")));
  create.addEventListener(
    "submit",
    guarded(async (event) => {
      event.preventDefault();
      for (const f of cFields) f.setError("");
      await ctx.act(
        async () => {
          const memberNo = text(cMember.input.value);
          const member = memberNo ? await findMember(memberNo) : null;
          return post(
            "/donors",
            omitNull({
              kind: cKind.input.value,
              name: cName.input.value.trim(),
              email: text(cEmail.input.value),
              phone: text(cPhone.input.value),
              member_id: member ? member.id : null,
              anonymous: cAnonymous.input.value === "true",
            }),
          );
        },
        (d) => `Donor ${d.name} created.`,
        () => {
          create.reset();
          return list.goTo(1);
        },
        (error) => {
          for (const [key, problem] of Object.entries(problems(error, { member_id: "member_no" }))) {
            cFields.find((f) => f.input.name === key)?.setError(problem);
          }
        },
      );
    }),
  );

  replace(ctx.body, section("New donor", create), section("Donors", filters, list.el));
  await list.goTo(1);
}

const donorsScreen = {
  id: "don-01",
  title: "Donors",
  module: "Donations",
  roles: ["librarian", "admin"],
  async render(ctx) {
    if (/^\d+$/.test(ctx.param)) await donorPage(ctx, Number(ctx.param));
    else await donorList(ctx);
  },
};

// ---- LIB-UI-DON-02 ---------------------------------------------------------------

const currentYear = (ctx) => Number(ctx.today.slice(0, 4));

/** One offered title: fields named like the API (`title`, `author_text`, `isbn`, `publication_year`, `condition`, `quantity`). */
function itemRow(ctx, item, onRemove, onChange) {
  const fields = {
    title: field({ name: "title", label: "Title", value: item.title ?? "", attrs: { maxlength: "300" } }),
    author_text: field({ name: "author_text", label: "Author", value: item.author_text ?? "", attrs: { maxlength: "200" } }),
    isbn: field({ name: "isbn", label: "ISBN", value: item.isbn ?? "", hint: "Optional." }),
    publication_year: field({
      name: "publication_year",
      label: "Year",
      type: "number",
      value: item.publication_year ?? "",
      min: 1450,
      max: currentYear(ctx),
    }),
    condition: field({ name: "condition", label: "Condition", options: choices(CONDITIONS), value: item.condition ?? "good" }),
    quantity: field({ name: "quantity", label: "Quantity", type: "number", value: item.quantity ?? 1, min: 1, max: 20 }),
  };
  const legend = h("legend", {});
  const remove = button("Remove title", () => onRemove(row));
  const row = {
    fields,
    remove,
    el: h(
      "fieldset",
      { class: "offer-item" },
      legend,
      h("div", { class: "form inline-form" }, Object.values(fields)),
      h("div", { class: "actions" }, remove),
    ),
    number(n) {
      replace(legend, `Title ${n}`);
    },
    read() {
      return {
        title: fields.title.input.value.trim(),
        author_text: fields.author_text.input.value.trim(),
        isbn: text(fields.isbn.input.value),
        publication_year: int(fields.publication_year.input.value),
        condition: fields.condition.input.value,
        quantity: int(fields.quantity.input.value),
      };
    },
  };
  fields.quantity.input.addEventListener("input", onChange);
  return row;
}

function itemsEditor(ctx) {
  const rows = [];
  const list = h("div", { class: "offer-items" });
  const summary = h("p", { class: "hint offer-total" });
  const add = button("Add title", () => addRow({}));

  function refresh() {
    rows.forEach((r, i) => {
      r.number(i + 1);
      r.remove.disabled = rows.length <= 1;
    });
    add.disabled = rows.length >= MAX_ITEMS;
    const copies = rows.reduce((sum, r) => sum + (Number(r.fields.quantity.input.value) || 0), 0);
    replace(summary, `${rows.length} of at most ${MAX_ITEMS} titles, ${copies} of at most 100 copies.`);
  }

  function addRow(item) {
    const row = itemRow(ctx, item, removeRow, refresh);
    rows.push(row);
    list.append(row.el);
    refresh();
    return row;
  }

  function removeRow(row) {
    if (rows.length <= 1) return;
    rows.splice(rows.indexOf(row), 1);
    row.el.remove();
    refresh();
  }

  return {
    el: h("div", { class: "offer-editor" }, list, h("div", { class: "actions" }, add), summary),
    set(items) {
      rows.length = 0;
      list.replaceChildren();
      for (const item of items.length ? items : [{}]) addRow(item);
    },
    read: () => rows.map((r) => r.read()),
    setErrors(map) {
      for (const r of rows) for (const f of Object.values(r.fields)) f.setError("");
      for (const [key, problem] of Object.entries(map)) {
        const m = /^items\.(\d+)\.(\w+)$/.exec(key);
        if (m) rows[Number(m[1])]?.fields[m[2]]?.setError(problem);
      }
    },
  };
}

const offerFormScreen = {
  id: "don-02",
  title: "Offer form",
  module: "Donations",
  roles: ["member", "librarian", "admin"],
  async render(ctx) {
    const branches = (await ctx.branches()).filter((b) => b.is_active);
    const map = await branchMap(ctx);
    const dir = donorDirectory();
    const me = ctx.isMember ? await get("/members/me") : null;
    let editing = null;

    const heading = h("h2", {}, "New offer");
    const donorBox = h("div", { class: "donor-choice" });
    const donorSelect = field({ name: "donor_id", label: "Donor", options: [{ value: "", label: "No donors" }] });
    const donorFind = field({ name: "q", label: "Find donor", hint: "Name or email; the first 100 matches are offered." });
    const branch = field({ name: "branch_id", label: "Branch", options: branchOptions(branches) });
    const note = field({ name: "note", label: "Note", type: "textarea", attrs: { maxlength: "500" }, hint: "At most 500 characters." });
    const items = itemsEditor(ctx);
    const submit = h("button", { type: "submit" }, "Offer");
    const discard = button("Stop editing", () => reset());
    discard.hidden = true;
    const formFields = [donorSelect, branch, note];

    async function loadDonors() {
      const data = await get("/donors", { is_active: "true", page_size: 100, q: donorFind.input.value.trim() });
      const options = data.items.filter((d) => !d.merged_into_id);
      const previous = donorSelect.input.value;
      donorSelect.input.replaceChildren(
        ...(options.length ? options : [{ id: "", name: "No donors" }]).map((d) =>
          h("option", { value: String(d.id) }, d.id === "" ? d.name : `${d.name} (#${d.id})`),
        ),
      );
      if (previous && options.some((d) => String(d.id) === previous)) donorSelect.input.value = previous;
    }

    function reset() {
      editing = null;
      replace(heading, "New offer");
      submit.textContent = "Offer";
      discard.hidden = true;
      donorBox.hidden = false;
      note.input.value = "";
      if (branches.length) branch.input.value = String(branches[0].id);
      items.set([]);
      for (const f of formFields) f.setError("");
      items.setErrors({});
    }

    async function startEdit(donation) {
      editing = donation;
      replace(heading, `Change offer ${donation.id}`);
      submit.textContent = "Save";
      discard.hidden = false;
      donorBox.hidden = true;
      if (![...branch.input.options].some((o) => o.value === String(donation.branch_id))) {
        branch.input.append(h("option", { value: String(donation.branch_id) }, branchName(map, donation.branch_id)));
      }
      branch.input.value = String(donation.branch_id);
      note.input.value = donation.note;
      items.set(donation.items);
      form.scrollIntoView?.({ block: "nearest" });
      branch.input.focus();
    }

    const form = h("form", { class: "form offer-form", novalidate: true, "data-form": "Offer" });
    if (ctx.isStaff) {
      const findButton = button("Find donor", () => loadDonors().catch((e) => ctx.fail(e)));
      donorFind.input.addEventListener(
        "keydown",
        guarded((event) => {
          if (event.key !== "Enter") return;
          event.preventDefault();
          return loadDonors().catch((e) => ctx.fail(e));
        }),
      );
      donorBox.append(h("div", { class: "form inline-form" }, donorFind, findButton), donorSelect);
      donorBox.append(h("p", { class: "hint" }, "A donor that does not exist yet is created on the ", link("Donors", "#/don-01"), " screen."));
      form.append(donorBox);
    }
    form.append(branch, note, h("h3", {}, "Titles"), items.el, h("div", { class: "actions" }, submit, discard));
    form.addEventListener(
      "submit",
      guarded(async (event) => {
        event.preventDefault();
        for (const f of formFields) f.setError("");
        items.setErrors({});
        const body = { branch_id: int(branch.input.value), note: note.input.value.trim(), items: items.read() };
        const onError = (error) => {
          const found = problems(error);
          items.setErrors(found);
          for (const f of formFields) if (found[f.input.name]) f.setError(found[f.input.name]);
        };
        if (editing) {
          const id = editing.id;
          await ctx.act(() => patch(`/donations/${id}`, body), `Offer ${id} saved.`, async () => {
            reset();
            await list.reload();
          }, onError);
        } else {
          if (ctx.isStaff && donorSelect.input.value !== "") body.donor_id = int(donorSelect.input.value);
          await ctx.act(
            () => post("/donations", body),
            (d) => `Offer ${d.id} sent with ${d.items_count} title(s) and ${d.copies_offered} copies. Status: ${d.status}.`,
            async () => {
              reset();
              await list.goTo(1);
            },
            onError,
          );
        }
      }),
    );

    const list = pagedTable({
      onError: (e) => ctx.fail(e),
      columns: donationColumns(map, {
        withDonor: ctx.isStaff,
        actions: (d) =>
          d.status === "offered"
            ? h(
                "span",
                { class: "row-actions" },
                button("Change", () => startEdit(d)),
                button("Cancel", () =>
                  ctx.ask({
                    text: `Cancel offer ${d.id}?`,
                    onConfirm: () =>
                      ctx.act(
                        () => post(`/donations/${d.id}/cancel`),
                        `Offer ${d.id} cancelled.`,
                        async () => {
                          if (editing && editing.id === d.id) reset();
                          await list.reload();
                        },
                      ),
                  }),
                ),
              )
            : "–",
      }),
      load: async (page) => {
        const data = ctx.isMember
          ? await get(`/members/${me.id}/donations`, { page, page_size: 20 })
          : await get("/donations", { status: "offered", page, page_size: 20 });
        if (ctx.isStaff) await dir.annotate(data.items);
        return data;
      },
    });

    replace(
      ctx.body,
      h("section", { class: "panel", "data-section": "Offer" }, heading, form),
      section(ctx.isMember ? "My offers" : "Open offers", list.el),
    );
    reset();
    if (ctx.isStaff) await loadDonors();
    await list.goTo(1);

    // `#/don-02/<id>` opens that offer for changing.
    if (/^\d+$/.test(ctx.param)) {
      const donation = await get(`/donations/${ctx.param}`);
      if (donation.status === "offered") await startEdit(donation);
      else ctx.body.prepend(h("p", { class: "hint" }, `Donation ${donation.id} is ${donation.status}; only offered donations can be changed.`));
    }
  },
};

// ---- LIB-UI-DON-03 ---------------------------------------------------------------

const DECISIONS = [
  { value: "", label: "Choose…" },
  { value: "accepted", label: "Accept" },
  { value: "declined", label: "Decline" },
];

/** One item of a review: decision, catalog book search, quantity and value per copy, or a decline reason. */
async function reviewItem(ctx, item, suggestion, number) {
  const suggested = suggestion?.decision || "";
  const decision = field({ name: "decision", label: "Decision", options: DECISIONS, value: suggested });
  const search = field({ name: "q", label: "Search the catalog", value: item.isbn || item.title, hint: "Title, author or ISBN." });
  const book = field({ name: "book_id", label: "Book", options: [{ value: "", label: "Choose a book" }] });
  const quantity = field({ name: "accepted_quantity", label: "Quantity accepted", type: "number", value: item.quantity, min: 1, max: item.quantity });
  const value = field({ name: "estimated_value", label: "Value per copy (TL)", inputmode: "decimal", hint: "0.01 to 5000.00" });
  const reason = field({
    name: "decline_reason",
    label: "Reason",
    options: [{ value: "", label: "Choose a reason" }, ...choices(DECLINE_REASONS)],
    value: suggested === "declined" ? suggestion.decline_reason || "" : "",
  });
  const found = h("p", { class: "hint book-hint" });

  const setBooks = (books, selectedId) => {
    book.input.replaceChildren(
      h("option", { value: "" }, "Choose a book"),
      ...books.map((b) => h("option", { value: String(b.id) }, `${b.title} (${b.isbn})`)),
    );
    book.input.value = selectedId ? String(selectedId) : "";
  };

  async function runSearch() {
    const data = await get("/search/books", { q: search.input.value.trim(), page_size: 20 });
    const books = data.items.map((r) => r.book);
    setBooks(books, books.length === 1 ? books[0].id : null);
    replace(
      found,
      books.length ? `${books.length} book(s) found.` : "No book found. ",
      books.length ? null : link("Add the book to the catalog", "#/cat-03"),
    );
  }
  search.input.addEventListener(
    "keydown",
    guarded((event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      return runSearch().catch((e) => ctx.fail(e));
    }),
  );

  if (suggestion?.book_id) {
    const suggestedBook = await ctx.book(suggestion.book_id).catch(() => null);
    if (suggestedBook) setBooks([suggestedBook], suggestedBook.id);
  }

  const acceptedBox = h(
    "div",
    { class: "form inline-form accept-fields" },
    search,
    button("Search", () => runSearch().catch((e) => ctx.fail(e))),
    book,
    quantity,
    value,
    found,
  );
  const declinedBox = h("div", { class: "form inline-form decline-fields" }, reason);
  const toggle = () => {
    acceptedBox.hidden = decision.input.value !== "accepted";
    declinedBox.hidden = decision.input.value !== "declined";
  };
  decision.input.addEventListener("change", toggle);
  toggle();

  const hint =
    suggestion && suggestion.decision
      ? `Suggestion: ${suggestion.decision === "accepted" ? "accept" : "decline"}${suggestion.decline_reason ? ` (${words(suggestion.decline_reason)})` : ""}.`
      : "No suggestion.";
  const el = h(
    "fieldset",
    { class: "review-item", "data-item": String(item.id) },
    h("legend", {}, `Item ${number}: ${item.title}`),
    h(
      "p",
      { class: "review-facts" },
      `Author: ${fmtText(item.author_text)}; ISBN: ${fmtText(item.isbn)}; year ${item.publication_year}; condition ${item.condition}; quantity ${item.quantity}. `,
      h("em", {}, hint),
    ),
    h("div", { class: "form inline-form" }, decision),
    acceptedBox,
    declinedBox,
  );

  function read() {
    const d = decision.input.value;
    const missing = (name, problem) =>
      clientError("VALIDATION_ERROR", `Item ${number} (${item.title}): ${problem}`, { fields: [{ field: name, problem: "field required" }] });
    if (!d) throw missing("decision", "choose accept or decline.");
    if (d === "declined") {
      if (!reason.input.value) throw missing("decline_reason", "choose a reason for declining.");
      return { item_id: item.id, decision: "declined", decline_reason: reason.input.value };
    }
    if (!book.input.value) throw missing("book_id", "search the catalog and choose the book.");
    return {
      item_id: item.id,
      decision: "accepted",
      book_id: int(book.input.value),
      accepted_quantity: int(quantity.input.value),
      estimated_value: text(value.input.value),
    };
  }
  return { el, read };
}

function itemsOverview(ctx, donation) {
  return table({
    caption: "Items",
    columns: [
      { label: "Title", value: (i) => i.title },
      { label: "Author", value: (i) => fmtText(i.author_text) },
      { label: "ISBN", value: (i) => fmtText(i.isbn) },
      { label: "Year", value: (i) => String(i.publication_year) },
      { label: "Condition", value: (i) => i.condition },
      { label: "Quantity", value: (i) => String(i.quantity) },
      { label: "Decision", value: (i) => i.decision },
      { label: "Decline reason", value: (i) => (i.decline_reason ? words(i.decline_reason) : "–") },
      { label: "Book", value: (i) => (i.book_id ? link(`Book ${i.book_id}`, `#/cat-02/${i.book_id}`) : "–") },
      { label: "Accepted", value: (i) => fmtText(i.accepted_quantity) },
      { label: "Value per copy", value: (i) => fmtAmount(i.estimated_value) },
      { label: "Received", value: (i) => String(i.received_quantity) },
    ],
    rows: donation.items,
  });
}

async function donationInfo(ctx, donation, dir, map) {
  return definitionList([
    ["Donation", String(donation.id)],
    ["Donor", donorLink(donation.donor_id, await dir.name(donation.donor_id))],
    ["Branch", branchName(map, donation.branch_id)],
    ["Status", donation.status],
    ["Offered at", fmtDateTime(donation.offered_at)],
    ["Note", fmtText(donation.note)],
    ["Reviewed at", fmtDateTime(donation.reviewed_at)],
    ["Expected by", fmtDate(donation.expected_by)],
    ["Cancel reason", donation.cancel_reason ? words(donation.cancel_reason) : "–"],
    ["Receipt", receiptLink(donation)],
  ]);
}

/** Select of donations by status for the screens that first ask which donation to open. */
async function donationChooser(ctx, statuses, route, intro) {
  const dir = donorDirectory();
  const lists = await Promise.all(statuses.map((status) => fetchAll("/donations", { status })));
  const donations = lists.flat().sort((a, b) => b.id - a.id);
  await dir.annotate(donations);
  const choose = field({
    name: "donation_id",
    label: "Donation",
    options: donations.length
      ? recordOptions(donations, (d) => `#${d.id} – ${d._donorName} – ${fmtDate(d.offered_at)} – ${d.copies_offered} copies (${d.status})`)
      : [{ value: "", label: "No donations" }],
  });
  const node = h("form", { class: "form", novalidate: true, "data-form": "Choose a donation" }, choose);
  node.append(h("div", { class: "actions" }, h("button", { type: "submit" }, "Open")));
  node.addEventListener(
    "submit",
    guarded((event) => {
      event.preventDefault();
      if (choose.input.value) ctx.navigate(`#/${route}/${choose.input.value}`);
    }),
  );
  return h("div", {}, intro ? h("p", {}, intro) : null, node);
}

const reviewScreen = {
  id: "don-03",
  title: "Review",
  module: "Donations",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    if (!/^\d+$/.test(ctx.param)) {
      replace(ctx.body, await donationChooser(ctx, ["offered"], "don-03", "Choose an offered donation to review."));
      return;
    }
    const id = Number(ctx.param);
    const map = await branchMap(ctx);
    const dir = donorDirectory();

    async function show() {
      const donation = await get(`/donations/${id}`);
      const parts = [
        h("p", {}, link("Offered donations", "#/don-03")),
        section(`Donation ${donation.id}`, await donationInfo(ctx, donation, dir, map)),
      ];
      if (donation.status !== "offered") {
        parts.push(
          section(
            "Items",
            h("p", {}, `This donation is ${donation.status}; only offered donations can be reviewed.`),
            itemsOverview(ctx, donation),
            donation.status === "accepted" || donation.status === "partially_received" ? link("Receive the copies", `#/don-04/${donation.id}`) : null,
          ),
        );
        replace(ctx.body, ...parts);
        return;
      }
      const suggestions = new Map((await get(`/donations/${id}/suggestions`)).items.map((s) => [s.item_id, s]));
      const panels = [];
      for (const [index, item] of donation.items.entries()) {
        panels.push(await reviewItem(ctx, item, suggestions.get(item.id), index + 1));
      }
      const node = h(
        "form",
        { class: "review-form", novalidate: true, "data-form": "Review" },
        h("p", { class: "hint" }, "Decide every item. Suggestions are filled in; change them where needed. When every item is declined the donation is rejected."),
        panels.map((p) => p.el),
        h("div", { class: "actions" }, h("button", { type: "submit" }, "Review")),
      );
      node.addEventListener(
        "submit",
        guarded(async (event) => {
          event.preventDefault();
          ctx.clearMessages();
          let body;
          try {
            body = { items: panels.map((p) => p.read()) };
          } catch (error) {
            ctx.fail(error);
            return;
          }
          await ctx.act(
            () => post(`/donations/${id}/review`, body),
            (d) =>
              d.status === "rejected"
                ? "Review saved. Every item was declined: the donation is rejected."
                : `Review saved. The donation is accepted; the copies are expected by ${fmtDate(d.expected_by)}.`,
            show,
          );
        }),
      );
      parts.push(section("Items to review", node));
      replace(ctx.body, ...parts);
    }
    await show();
  },
};

// ---- LIB-UI-DON-04 ---------------------------------------------------------------

const receivingScreen = {
  id: "don-04",
  title: "Receiving desk",
  module: "Donations",
  roles: ["librarian", "admin"],
  desk: true,
  async render(ctx) {
    const map = await branchMap(ctx);
    const dir = donorDirectory();
    const processBox = section(
      "Late donations",
      h("p", { class: "hint" }, "Accepted donations whose expected date has passed are set to expired; received copies stay."),
      button("Process", () =>
        ctx.act(
          () => post("/donations/process"),
          (r) => `${r.expired} donation(s) expired.`,
          () => show(),
        ),
      ),
    );
    const area = h("div", { class: "receiving-area" });
    replace(ctx.body, processBox, area);

    async function showList() {
      const lists = await Promise.all(["accepted", "partially_received"].map((status) => fetchAll("/donations", { status })));
      const donations = lists.flat().sort((a, b) => (a.expected_by || "").localeCompare(b.expected_by || "") || a.id - b.id);
      await dir.annotate(donations);
      replace(
        area,
        section(
          "Expected donations",
          table({
            columns: [
              { label: "ID", value: (d) => String(d.id) },
              { label: "Donor", value: (d) => donorLink(d.donor_id, d._donorName) },
              { label: "Branch", value: (d) => branchName(map, d.branch_id) },
              { label: "Status", value: (d) => d.status },
              {
                label: "Expected by",
                value: (d) => (d.expected_by && d.expected_by < ctx.today ? `${fmtDate(d.expected_by)} (late)` : fmtDate(d.expected_by)),
              },
              {
                label: "Copies still expected",
                value: (d) => String(d.items.reduce((sum, i) => sum + (i.decision === "accepted" ? i.accepted_quantity - i.received_quantity : 0), 0)),
              },
              { label: "Actions", value: (d) => link("Receive", `#/don-04/${d.id}`) },
            ],
            rows: donations,
            rowClass: (d) => (d.expected_by && d.expected_by < ctx.today ? "overdue" : undefined),
          }),
        ),
      );
    }

    async function showDonation(id) {
      const donation = await get(`/donations/${id}`);
      const open = donation.status === "accepted" || donation.status === "partially_received";
      const parts = [
        h("p", {}, link("Expected donations", "#/don-04")),
        section(`Donation ${donation.id}`, await donationInfo(ctx, donation, dir, map), itemsOverview(ctx, donation)),
      ];
      if (!open) {
        parts.push(h("p", {}, `This donation is ${donation.status}; nothing can be received.`));
        replace(area, ...parts);
        return;
      }
      const pending = new Map();
      const blocks = [];
      for (const item of donation.items) {
        if (item.decision !== "accepted") continue;
        const remaining = item.accepted_quantity - item.received_quantity;
        const barcodes = [];
        pending.set(item.id, barcodes);
        const input = field({ name: "barcode", label: `Barcode for ${item.title}`, attrs: { autocomplete: "off" } });
        const chips = h("ul", { class: "pending-barcodes" });
        const drawChips = () => {
          replace(
            chips,
            barcodes.map((code, index) =>
              h(
                "li",
                {},
                h("code", {}, code),
                " ",
                button("Remove", () => {
                  barcodes.splice(index, 1);
                  drawChips();
                }, { "aria-label": `Remove barcode ${code}` }),
              ),
            ),
          );
        };
        const addBarcode = () => {
          const code = input.input.value.trim();
          if (!code) return;
          barcodes.push(code);
          input.input.value = "";
          drawChips();
          input.input.focus();
        };
        input.input.addEventListener(
          "keydown",
          guarded((event) => {
            if (event.key !== "Enter") return;
            event.preventDefault();
            addBarcode();
          }),
        );
        blocks.push(
          h(
            "fieldset",
            { class: "receive-item", "data-item": String(item.id) },
            h("legend", {}, `${item.title} (${fmtText(item.isbn)})`),
            h(
              "p",
              { class: remaining > 0 ? "still-expected" : "hint" },
              `Accepted ${item.accepted_quantity}, received ${item.received_quantity}, still expected ${remaining}. Value per copy ${fmtAmount(item.estimated_value)}.`,
            ),
            remaining > 0
              ? h("div", { class: "form inline-form" }, input, button("Add barcode", addBarcode))
              : null,
            remaining > 0 ? chips : null,
          ),
        );
      }
      const receive = button("Receive", () => {
        const items = [...pending.entries()].filter(([, codes]) => codes.length).map(([item_id, barcodes]) => ({ item_id, barcodes: [...barcodes] }));
        if (!items.length) {
          ctx.fail(clientError("VALIDATION_ERROR", "Scan at least one barcode.", { fields: [{ field: "barcodes", problem: "field required" }] }));
          return undefined;
        }
        return ctx.act(
          () => post(`/donations/${id}/receive`, { items }),
          (d) =>
            `Received ${items.reduce((n, i) => n + i.barcodes.length, 0)} copy/copies. Status: ${d.status}.${d.receipt_no ? ` Receipt ${d.receipt_no}.` : ""}`,
          () => showDonation(id),
        );
      });
      const actions = h("div", { class: "actions" }, receive);
      if (donation.status === "accepted") {
        actions.append(
          button("Cancel", () =>
            ctx.ask({
              text: `Cancel donation ${donation.id}? No copies have been received yet.`,
              onConfirm: () => ctx.act(() => post(`/donations/${id}/cancel`), `Donation ${id} cancelled.`, () => showDonation(id)),
            }),
          ),
        );
      }
      parts.push(
        section(
          "Scan the copies",
          h("p", { class: "hint" }, `Scan or type a barcode per copy and press Enter. The copies are expected by ${fmtDate(donation.expected_by)}.`),
          ...blocks,
          actions,
        ),
      );
      replace(area, ...parts);
    }

    async function show() {
      if (/^\d+$/.test(ctx.param)) await showDonation(Number(ctx.param));
      else await showList();
    }
    await show();
  },
};

// ---- LIB-UI-DON-05 ---------------------------------------------------------------

async function receiptView(ctx, id) {
  const map = await branchMap(ctx);
  const back = h("p", { class: "no-print" }, link(ctx.isStaff ? "All donations" : "My donations", "#/don-05"));
  replace(ctx.body, back);
  const receipt = await get(`/donations/${id}/receipt`);
  const donor = ctx.isStaff ? donorLink(receipt.donor.id, receipt.donor.name) : receipt.donor.name;
  const panel = section(
    `Receipt ${receipt.receipt_no ?? ""}`.trim(),
    definitionList([
      ["Receipt number", fmtText(receipt.receipt_no)],
      ["Donation", String(id)],
      ["Donor", donor],
      ["Kind", words(receipt.donor.kind)],
      ["Branch", branchName(map, receipt.branch_id)],
      ["First received on", fmtDate(receipt.first_received_on)],
      ["Last received on", fmtDate(receipt.last_received_on)],
    ]),
    table({
      columns: [
        { label: "Title", value: (l) => l.title },
        { label: "Copies", value: (l) => String(l.copies) },
        { label: "Value per copy", value: (l) => fmtAmount(l.value_per_copy) },
        { label: "Value", value: (l) => fmtAmount(l.value) },
      ],
      rows: receipt.lines,
    }),
    h("p", { class: "total" }, `Total copies: ${receipt.total_copies}. Total value: ${fmtAmount(receipt.total_value)}.`),
    h("div", { class: "actions no-print" }, button("Print", () => window.print())),
  );
  panel.classList.add("receipt");
  back.after(panel);
}

const receiptScreen = {
  id: "don-05",
  title: "Receipt and my donations",
  module: "Donations",
  roles: ["member", "librarian", "admin"],
  async render(ctx) {
    if (/^\d+$/.test(ctx.param)) {
      await receiptView(ctx, Number(ctx.param));
      return;
    }
    const map = await branchMap(ctx);
    const receiptAction = (d) => (d.receipt_no ? link("Receipt", `#/don-05/${d.id}`) : "–");
    if (ctx.isMember) {
      const me = await get("/members/me");
      const list = pagedTable({
        onError: (e) => ctx.fail(e),
        columns: donationColumns(map, { actions: receiptAction }),
        load: (page) => get(`/members/${me.id}/donations`, { page, page_size: 20 }),
      });
      replace(ctx.body, section("My donations", list.el));
      await list.goTo(1);
      return;
    }
    const dir = donorDirectory();
    const number = field({ name: "donation_id", label: "Donation number", inputmode: "numeric" });
    const open = h("form", { class: "form", novalidate: true, "data-form": "Open a receipt" }, number);
    open.append(h("div", { class: "actions" }, h("button", { type: "submit" }, "Open")));
    open.addEventListener(
      "submit",
      guarded((event) => {
        event.preventDefault();
        ctx.clearMessages();
        const value = number.input.value.trim();
        if (/^\d+$/.test(value)) ctx.navigate(`#/don-05/${value}`);
        else ctx.fail(clientError("VALIDATION_ERROR", "Enter the donation number.", { fields: [{ field: "donation_id", problem: "field required" }] }));
      }),
    );
    const status = field({ name: "status", label: "Status", options: choices(DONATION_STATUSES, { any: "Any" }) });
    const filters = h("form", { class: "form filters", novalidate: true, "data-form": "Donation filters" }, status);
    filters.append(h("div", { class: "actions" }, h("button", { type: "submit" }, "Filter")));
    filters.addEventListener(
      "submit",
      guarded((event) => {
        event.preventDefault();
        return reloadList();
      }),
    );
    const listBox = h("div", {});
    function reloadList() {
      const table2 = pagedTable({
        onError: (e) => ctx.fail(e),
        columns: donationColumns(map, { withDonor: true, actions: receiptAction }),
        load: async (page) => {
          const data = await get("/donations", { page, page_size: 20, status: status.input.value });
          await dir.annotate(data.items);
          return data;
        },
      });
      replace(listBox, table2.el);
      return table2.goTo(1);
    }
    replace(ctx.body, section("Print a receipt", open), section("Donations", filters, listBox));
    await reloadList();
  },
};

// ---- LIB-UI-DON-06 ---------------------------------------------------------------

const wallScreen = {
  id: "don-06",
  title: "Donor wall and reports",
  module: "Donations",
  roles: ["all"],
  async render(ctx) {
    const thisYear = currentYear(ctx);

    // ---- donor wall (all users)
    const wallYear = field({ name: "year", label: "Year", type: "number", value: thisYear, min: 2000, max: 2100 });
    const wallOut = h("div", { class: "donor-wall" });
    const wallForm = h("form", { class: "form filters", novalidate: true, "data-form": "Donor wall" }, wallYear);
    wallForm.append(h("div", { class: "actions" }, h("button", { type: "submit" }, "Show")));
    wallForm.addEventListener(
      "submit",
      guarded(async (event) => {
        event.preventDefault();
        ctx.clearMessages();
        wallYear.setError("");
        try {
          const wall = await get("/donor-wall", { year: wallYear.input.value.trim() });
          replace(
            wallOut,
            table({
              caption: `Donors of ${wall.year}`,
              columns: [
                { label: "Name", value: (d) => d.name },
                { label: "Level", value: (d) => levelText(d.level) },
              ],
              rows: wall.donors,
            }),
            h("p", { class: "anonymous-count" }, `Anonymous donors: ${wall.anonymous_count}`),
          );
        } catch (error) {
          replace(wallOut);
          wallYear.setError(problems(error).year || "");
          ctx.fail(error);
        }
      }),
    );
    const parts = [section("Donor wall", wallForm, wallOut)];

    if (ctx.isStaff) {
      const map = await branchMap(ctx);

      // ---- donations report
      const from = field({ name: "from", label: "From", type: "date", value: `${thisYear}-01-01` });
      const to = field({ name: "to", label: "To", type: "date", value: ctx.today });
      const repOut = h("div", { class: "report" });
      const repList = pagedTable({
        onError: (e) => {
          replace(repOut);
          ctx.fail(e);
        },
        columns: [
          { label: "Branch", value: (r) => branchName(map, r.branch_id) },
          { label: "Donations", value: (r) => String(r.donations) },
          { label: "Copies offered", value: (r) => String(r.copies_offered) },
          { label: "Copies accepted", value: (r) => String(r.copies_accepted) },
          { label: "Copies received", value: (r) => String(r.copies_received) },
          { label: "Value received", value: (r) => fmtAmount(r.value_received) },
          { label: "Declined: duplicate", value: (r) => String(r.declined.duplicate) },
          { label: "Declined: poor condition", value: (r) => String(r.declined.poor_condition) },
          { label: "Declined: out of scope", value: (r) => String(r.declined.out_of_scope) },
          { label: "Declined: too old", value: (r) => String(r.declined.too_old) },
          { label: "Declined: other", value: (r) => String(r.declined.other) },
        ],
        load: (page) => get("/reports/donations", { page, page_size: 50, from: from.input.value, to: to.input.value }),
      });
      const repForm = h("form", { class: "form filters", novalidate: true, "data-form": "Donations report" }, from, to);
      repForm.append(h("div", { class: "actions" }, h("button", { type: "submit" }, "Show")));
      repForm.addEventListener(
        "submit",
        guarded((event) => {
          event.preventDefault();
          ctx.clearMessages();
          replace(repOut, repList.el);
          return repList.goTo(1);
        }),
      );

      // ---- donor report
      const year = field({ name: "year", label: "Year", type: "number", value: thisYear, min: 2000, max: 2100 });
      const donorOut = h("div", { class: "report" });
      const donorList = pagedTable({
        onError: (e) => {
          replace(donorOut);
          ctx.fail(e);
        },
        columns: [
          { label: "Donor", value: (r) => donorLink(r.donor_id, r.name) },
          { label: "Kind", value: (r) => words(r.kind) },
          { label: "Value", value: (r) => fmtAmount(r.value) },
          { label: "Level", value: (r) => levelText(r.level) },
          { label: "Copies", value: (r) => String(r.copies) },
        ],
        load: (page) => get("/reports/donors", { page, page_size: 50, year: year.input.value.trim() }),
      });
      const donorForm = h("form", { class: "form filters", novalidate: true, "data-form": "Donor report" }, year);
      donorForm.append(h("div", { class: "actions" }, h("button", { type: "submit" }, "Show")));
      donorForm.addEventListener(
        "submit",
        guarded((event) => {
          event.preventDefault();
          ctx.clearMessages();
          replace(donorOut, donorList.el);
          return donorList.goTo(1);
        }),
      );

      parts.push(section("Donations report", repForm, repOut), section("Donor report", donorForm, donorOut));
      replace(ctx.body, ...parts);
      wallForm.requestSubmit();
      repForm.requestSubmit();
      donorForm.requestSubmit();
      return;
    }
    replace(ctx.body, ...parts);
    wallForm.requestSubmit();
  },
};

export const donationScreens = [donorsScreen, offerFormScreen, reviewScreen, receivingScreen, receiptScreen, wallScreen];
