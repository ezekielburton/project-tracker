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
