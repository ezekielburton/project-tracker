# HSE & Compliance module

Registers, inspections and compliance for the site HSE officer. Off-roadmap;
ships as a patch against whatever release it lands in.

## Shape

Twenty-one near-identical registers are one table plus one declaration.

- `HSE_REGISTERS` (`lib/registers.py`) declares each register: key, label, rail
  group, ref prefix, how its status is arrived at, and its fields. Forms,
  tables, filters and validation render from it. **Adding a register is one
  entry here, not a feature.**
- `HseEntry` holds every entry. A field is a real column when it is shared
  across registers or is a foreign key; everything else lands in `data` (JSONB).

**Person and asset references are always FK columns, never JSONB.** An id inside
JSONB has no referential integrity and rots the first time a record is merged.

**So is any name that has to track its source.** The compliance certificate sits
behind `compliance_item_id` — a `HseReference` of kind `compliance_item` — rather
than as text in `data`, so renaming a certificate carries its whole renewal
history with it instead of forking a new one. A choice in JSONB stores the label,
frozen at write time; only an FK-backed one survives a rename. Text that is
genuinely free text (the Tools and Materials `item` fields) stays in `data`.

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
- `none` — a log with no status at all (mileage, costs, toolbox talks). No chips,
  no days-open column, and excluded from the rail's open counts.

Read it through `computed.effective_status(entry, register)`, never off the
column directly.

## Waiting on someone else

`waiting_on_id` + `waiting_since` park an entry with a person flagged
`can_hold_actions`. That time is reported on its own and is excluded from
`days_owned`, so the SLA clock pauses. The performance page measures what the
officer controls; a decision he chased for six weeks is not his delay.

## The dashboards read one entry set

`lib/metrics.py` holds the definitions so the Overview, the calendar and My
performance cannot quote different numbers for the same word. **That is not
enough on its own:** a shared function still gives two answers if each page hands
it a different set of rows, which is exactly what happened when the two pages
loaded 400 and 800 days. The loader is shared too — `dashboard_entries()` in
`lib/query.py` — and a page that needs a longer window passes it as an argument.

**Anything carrying a due date is loaded whatever its issue date.** `entry_date`
on a certificate is when it was *issued*, so a window on that date drops a
five-year licence out of the very number meant to count it.

**Compliance health is one row per certificate, not one per renewal.** Renewing
files a new entry and leaves the old one in the register, so counting both makes
renewing *lower* the score — the superseded row reads as lapsed beside its valid
replacement. `_expiring()` keeps the latest filing per `compliance_item_id`
(later `entry_date`, and on a tie the higher id); an entry with no certificate
set counts on its own.

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
refresh and can be pasted to someone. Search and paging are server-side too —
see the filter pass at the end of this file.

**Lists are eager-loaded in one round trip** (`lib/query.py`): a row shows five
related records, and lazy-loading them is the N+1 the dashboard module is being
rebuilt to undo.

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
- **Preview reuses the app's one file-preview modal.** `openFilePreview` is
  already global from `base.html` — the same modal the project reference files
  open — so the Preview button on an attachment row needed only a route.
  `/hse/files/<id>/preview` serves the same bytes inline and returns JSON with a
  reason for a type it cannot render or a NAS read that fails, which is the
  contract that modal reads. Previewable is images and PDF (`PREVIEWABLE` in
  `lib/files.py`); Office and video stay downloads, because converting them is
  the projects module's preview-cache job.


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

Six things bite every time, and all six have bitten already.

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

**An SVG with a fixed pixel height gets letterboxed, not filled.** Give a chart
`width="100%"` and `height="300"` and the browser scales the whole drawing down
to fit 300px and centres it — so a 556-wide chart sat 1:1 in the middle of a
1160px card with dead space either side, which reads as a rendering bug rather
than a sizing one. Set `width="100%"`, no height attribute, and `height: auto`
in CSS: the viewBox aspect then sets the height and the chart fills the card.

**Size a chart's viewBox to the width it will render at.** Everything inside an
SVG scales with it, type included, so a chart drawn 556 wide and stretched
across 1160px renders its 9px labels at 19px. `lib/charts.py` takes a `width`
and the two surfaces pass their own — `SCREEN_WIDTH` for the page,
`PRINT_WIDTH` for the A4 report — rather than sharing one and hoping.

**A page fills the shell by opting in.** `.hse-main` is a flex column and
`.hse-inner--fill` makes the inner block take the remaining height, so panels
stretch to the bottom instead of floating at the top of an empty shell. Only
My performance uses it today; every other page keeps content-height behaviour.

**A page fills by measurement, not by flexbox.** `.hse-inner--fill` opts a page
in, but the height itself comes from `core/shared/js/fill_height.js` — asked
for in `hse_nav.js`, **outside** the double-wiring guard. The listener is wired
once; every SPA swap lands on a fresh box that has to be measured again, so a
call behind that guard works on first load and silently stops after a tab
click. `.main-content` is a flex item with no definite height, so a pure CSS
chain just grows to its content and scrolls the page — which also drags a wide
table's horizontal scrollbar below the fold.

---

## The register surface, after the filter pass

`/hse/<group>/<register>` takes `status`, `severity`, `year`, `q` and `page`,
all as URL parameters, so a filtered view survives a refresh and can be pasted
to someone else. Nothing is held in JavaScript.

- **`lib/query.py` owns filtering and paging**, not the route, so the chip
  counts and the rows they filter can never be built from two different sets.
  `page_of()` returns rows, counts and page arithmetic together.
- **Chip counts ignore the status filter** and honour the others — a chip shows
  how many rows it would land on, not how many exist.
- **Search is server-side.** It had to be: client-side search over a paged
  table only searches the page on screen, which quietly returns nothing. It
  covers the ref, the whole JSONB blob, and the names behind the foreign keys —
  the compliance certificate included, which is a reference row and not text in
  the blob; the seven outer joins only go on when someone is actually searching.
- **A stored status is SQL; a computed expiry status is not.** `status_source
  == 'expiry'` is a function of `due_at` and today, so that branch loads the
  matching rows and pages in Python. Compliance is the only expiry register and
  it holds certificates, not events, so the set stays small by nature.
- **Every link is built in the route**, not reassembled in the template — a new
  filter is one entry in `carried`, and a chip clears `page` so filtering to
  eleven rows while sitting on page 3 cannot show an empty table.
