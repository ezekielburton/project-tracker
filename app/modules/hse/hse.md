# HSE & Compliance module

Registers, inspections and compliance for the site HSE officer. Off-roadmap;
ships as a patch against whatever release it lands in.

## Shape

Twenty-one near-identical registers are one table plus one declaration.

- `HSE_REGISTERS` (`lib/registers.py`) declares each register: key, label, rail
  group, ref prefix, how its status is arrived at, and its fields. Forms,
  tables, filters and the importer render from it. **Adding a register is one
  entry here, not a feature.**
- `HseEntry` holds every entry. A field is a real column when it is shared
  across registers or is a foreign key; everything else lands in `data` (JSONB).

**Person and asset references are always FK columns, never JSONB.** An id inside
JSONB has no referential integrity and rots the first time a record is merged.

## Nothing derived is ever stored

Days open, days to expiry, expiry status, severity score, time waiting and time
owned are all computed in `lib/computed.py`. The source workbook stores these as
formulas, which is exactly why several of its columns disagree with their own
data.

## Status: stored or computed

A register declares `status_source`:

- `stored` — the officer sets it, from the register's own `statuses` tuple.
- `expiry` — Valid / Expiring soon / Expired, a pure function of `due_at`.
  Nothing writes the `status` column for these registers.

Read it through `computed.effective_status(entry, register)`, never off the
column directly.

## Waiting on someone else

`waiting_on_id` + `waiting_since` park an entry with a person flagged
`can_hold_actions`. That time is reported on its own and is excluded from
`days_owned`, so the SLA clock pauses. The performance page measures what the
officer controls; a decision he chased for six weeks is not his delay.

## Refs

`lib/refs.next_ref(register_key)` bumps a per-register counter with one atomic
`INSERT … ON CONFLICT DO UPDATE … RETURNING`. The unique constraint on
`(register, ref)` is the backstop, not the mechanism. Do not copy the job-number
`MAX()+1` pattern — its own comment flags it as racy.

## Reference data

`HseReference` is one table keyed by `kind`; a new simple list is a new kind,
not a migration. `HseAsset` is the physical things several registers point at.
Both are deactivated rather than deleted — existing entries still point at them.

The officer maintains all of it himself, gated `manage_hse`, on the module's own
page. Not the admin panel: that is `admin_panel`-gated, and an officer who needs
an admin to add a location will keep his locations in a spreadsheet.

## Gating

- `view_hse` — reads every register. hse, management, admin.
- `manage_hse` — creates and edits entries and lists. hse, admin.

Management reads but does not write. My performance is a relationship, not a
capability: a person always sees their own page; management and admin see
anyone's.

## Cross-module reads

`services/feed.py` is the only sanctioned way another module reads HSE numbers.
Never another module's models.

## The register surface

One route set serves all twenty-one registers:

```
/hse/                                 -> the first declared register
/hse/<group>                          -> that group's first register
/hse/<group>/<register>[?status=...]  -> the page
```

Columns, filter chips and the empty state all render from the declaration
(`lib/table.py` turns it into headers and cells), so the templates never name
a register or a field.

**The rail builds itself from HSE_REGISTERS.** A group with a declared register
links; a group without one renders as a non-link placeholder, so the officer can
see what is coming without a dead link. The rail itself is the shared
`.module-rail` — see `_shared_macros.html`.

**Status chips are links, not client-side filters.** The filter then survives a
refresh and can be pasted to someone. Search is client-side over the rows already
on the page.

**Lists are eager-loaded in one round trip** (`lib/query.py`): a row shows five
related records, and lazy-loading them is the N+1 the dashboard module is being
rebuilt to undo. `ROW_LIMIT` caps a page at the 500 most recent entries.

## Front-end notes

`hse.css` is in `test_dark_mode_css.py`'s `SWEPT_FILES`, so no hard-coded hex —
role tokens only. Two things worth knowing:

- The table turns OFF `.data-table`'s frozen first column. Freezing gives column
  one its own background per row state while the others stay transparent, and the
  two shades read as a divider — the seam found on the DI Performance table.
- The overdue day count is bold, not red. `--poppy` has no dark override and is
  too light for small text on white, and there is no semantic danger-text token
  in the app; the severity and status pills carry the colour instead.

`hse_registers.js` is an IIFE with no `DOMContentLoaded` gate (spa-navigation.md,
trap 1). The shared rail SPA-navigates itself via `core/shared/js/module_rail.js`;
the tab strip and chips are plain links outside that, so this file routes them
through `navigateTo` with a document-delegated, guarded listener.

## Demo data

`python seed_hse_demo.py` fills the three registers; `--wipe` removes only the
entries it made (they carry a `_demo` marker in their JSONB). The lists, people
and assets it creates are left alone — those are real reference data to keep.


## Attachments

Files filed against an entry live on the NAS under **`/HSE/<register label>/<ref>`**,
uploaded through `core/shared/services/nas.py`'s `upload_app_file`. `HseAttachment`
is the record of where they went, and it stores the **full path** rather than
rebuilding it on read — relabelling a register later cannot orphan a file.

- `lib/files.py` owns the path and the allowlist. `safe_segment()` is what stops
  a filename or a ref climbing out of the officer's folder.
- Downloads **stream through the app**, never a direct NAS link, so `view_hse` is
  actually enforced.
- Uploads are synchronous: this is evidence on a compliance record, so the
  officer waits and learns whether it landed. A NAS failure returns 502 and says
  so rather than showing success over nothing.
- Deleting removes the row first; `delete_app_file` never raises, so an
  unreachable NAS leaves an orphaned file rather than a row pointing at
  something the officer believes is gone.
- Attachments need an entry to hang off, so they appear once it exists. Creating
  an entry reopens the overlay in edit mode rather than closing, which keeps
  "file it, then attach the report" one continuous job.


## Lists & people

The officer maintains his own reference data at `/hse/lists`, gated `manage_hse`.
Not the admin panel: that is `admin_panel`-gated, and an officer who needs an
admin to add a location keeps his locations in a spreadsheet.

- **Nothing is ever deleted.** Entries already filed still point at a value, so a
  retired one is deactivated and stops being offered — the same rule CS Scopes
  follows.
- **Tabs are Locations, Departments, People, Assets and Other lists.** Every
  reference kind beyond the first two shares "Other lists", so declaring a
  register with a new choice list never means editing `lib/lists.py`. A test
  asserts every kind in `REFERENCE_KINDS` is reachable from some tab.
- **Quick-add sits inside the entry form too.** A missing type gets noticed
  mid-entry; sending him to another page to add one is how the real answer ends
  up typed into the description instead. `find_or_revive_reference()` reuses an
  existing name and revives a deactivated one, so quick-adding something that
  already exists can never leave the dropdown showing it twice.

**Severity and statuses are deliberately not here.** Severity drives the SLA
clock and the performance page; statuses drive the filter chips and every open
count (`OPEN_STATUSES` in `lib/query.py`). Both are closed sets in the
declaration, so changing one is a decision and a code change rather than a text
box. There is a test that fails if either turns up as an editable list.

## Building another page in this module

Three things bite every time, and all three have bitten already.

**A table needs `data-table`, not just `hse-table`.** `data-table` (main.css) is
where the padding, the mono uppercase header, the row borders, the hover and the
sticky head live. `hse-table` on its own is only the HSE override that turns
*off* the frozen first column. The Schedule tab shipped with `hse-table` alone
and rendered as bare text in a grid. Copy the class list from `_table.html`.

**Never name a view-model key `items`** — or `keys`, `values`, `get`, `copy`,
`update`, or anything else on a dict. Jinja resolves an attribute before a
subscript, so `{{ drawer.items }}` hands the template `dict.items`, the bound
method, and the page dies with "object of type 'builtin_function_or_method' has
no len()" several files from the cause. The calendar's lists are called
`day_items`; `shadowed_keys()` in `lib/calendar.py` and a test in
`test_hse_calendar.py` check every dict this module hands a template.

**Tabs and chips need `hse_nav.js`.** The shared rail routes itself through
`module_rail.js`, but `.hse-tab` and `.hse-chip` are plain links outside that
system — without the script every tab click is a full page reload. It is a
separate file precisely so a new page can load it without dragging in the
register surface's search code.
