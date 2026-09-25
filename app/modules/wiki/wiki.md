# wiki

The internal wiki: browsing published sections and articles, and a full editor
for authors to create, edit, publish, and delete sections and articles
(including inline image and self-hosted video upload).

## Structure
```
app/modules/wiki/
  routes/wiki.py            # the `wiki` blueprint (wiki_bp)
  lib/blocks.py             # Editor.js document shape, conversion, sanitising
  lib/article_templates.py  # the How-to / Reference / Blank skeletons
  lib/help_keys.py          # the help-key registry and coverage figures
  static/js/wiki.js         # reader, dashboard CRUD, slug, publish/delete
  static/js/wiki_editor.js  # Editor.js setup for the article editor
  static/js/block_drag.js   # capture-phase block dragging inside the editor
  static/js/editor_autosave.js
  static/js/editor_dashboard.js
  static/js/help_tray.js    # loaded by base.html, not by the wiki templates
  static/js/blocks/         # helix_callout.js, helix_video.js — our two tools
  templates/wiki/           # index, _article_content, editor_dashboard,
                            # editor_article, _section_modal, _article_modal,
                            # _coverage_panel, _help_article, _help_empty,
                            # _help_browse
  tests/test_wiki_smoke.py
  tests/test_wiki_blocks.py
  tests/test_wiki_editor.py
  tests/test_wiki_authoring.py
  tests/test_wiki_dashboard.py
  tests/test_wiki_help_keys.py
  tests/test_wiki_help_tray.py
  tests/test_wiki_editor_access.py
  wiki.md
```

## Routes (the `wiki` blueprint)
- `GET /wiki` — the reader view (published sections/articles)
- `GET /wiki/article/<id>` — one article's content
- `POST /wiki/upload-image` — inline image upload for the editor
- `POST /wiki/upload-video` — self-hosted video upload for the Video block
  (admin-only, mp4/webm, 200MB cap). Saves local-first to
  `static/wiki-uploads/videos/` and backs up to `/Admin/OVP/Wiki` on a
  background thread. The editor's Video block toggles between Embed URL and
  Upload File (`block.source`).
- `POST /wiki/editor/article/autosave` — parks the working copy in the
  article's draft; creates the article first if it does not exist yet. Writes
  through the ORM with `updated_at` assigned to itself, so the reader's Last
  Updated never moves.
- `GET /wiki/help` — every readable article, for the Help pill
- `GET /wiki/help/<key>` — the article claiming that key, or the gap plus a
  "Write this article" shortcut for admins
- `GET /wiki/editor` — the editor dashboard; `?help_key=` opens the
  new-article overlay with that key already chosen
- `POST /wiki/editor/article/create` — from the new-article overlay; seeds the
  chosen skeleton and redirects into the editor
- `POST /wiki/editor/sections/reorder`, `POST /wiki/editor/articles/reorder` —
  each takes an ordered list of ids and writes `sort_order` from list position
- article CRUD under `/wiki/editor/article/...` (edit, save, autosave,
  toggle-publish, delete) and `POST /wiki/editor/section/save` plus the
  section toggle-publish and delete endpoints

## Models
`WikiSection`, `WikiArticle`, from `core/shared`. Article content lives in
`sections_json` as an Editor.js document; `draft_sections_json` holds the
autosaved working copy (cleared when Save makes it live) and
`legacy_sections_json` the pre-Editor.js content as a fallback. `help_key`
names the page an article explains.

## Content format
`lib/blocks.py` owns the block format: `load_blocks` parses stored content for
the renderer, `to_editorjs` converts the old block array, `clean_html` applies
the inline allowlist (nh3) to editor text, and `sanitize_document` cleans a
whole document on save — dropping unknown blocks and unsafe media URLs. Block
types: `paragraph`, `header`, `list`, `image`, `helixCallout`, `helixVideo`.

Video embeds are host-checked, not substring-matched: `EMBED_HOSTS` allows
youtube.com, youtu.be and vimeo.com, matched against the parsed hostname, and
anything else renders as a plain link. `load_blocks` re-checks on read, so
content migrated in before the save gate existed is judged too.

## Editor
`editor_article.html` mounts Editor.js, pinned by exact version and loaded from
jsDelivr: editorjs 2.30.7, header 2.8.9, list 1.9.0, image 2.10.3. Each is
loaded with a subresource integrity hash and `crossorigin="anonymous"`, so a
changed file on the CDN is refused rather than run. `header` is
fixed to level 3, and `list` 1.x stores items as plain strings. Image and video
uploads reuse the existing endpoints — the image tool goes through an
`uploader.uploadByFile` hook so `/wiki/upload-image` keeps its response shape.
`wiki_editor.js` declares `TEMPLATE_CONTRACT`, the template ids it binds to;
`tests/test_wiki_editor.py` reads that list and checks the template.

## Authoring
New articles start from a skeleton in `lib/article_templates.py` — How-to,
Reference or Blank — picked in the new-article overlay and written into the
article when it is created. Saving and publishing are one action: a Published tick box posts
with the form, and the save clears the draft. Slugs are derived from the title
on create and never change afterwards, so links to an article keep working.

## Editor dashboard
Sections and their articles are reordered by dragging (Sortable.js, loaded
globally by `base.html`), and the order saves on drop — `sort_order` is never
typed. Section metadata and new articles are handled in overlays on the
dashboard using the app's standard modal (`.modal-overlay` / `.modal-box`, plus
`.wiki-modal` for the wiki's own spacing), so there are no separate form pages.
`editor_dashboard.js` declares `TEMPLATE_CONTRACT`, the ids it binds to across
the three templates; `tests/test_wiki_dashboard.py` reads that list and checks
the markup.

A section's Relevant roles are stored as role keys, and the picker is built from
`ROLE_LABELS` in `core/shared/lib/capabilities.py` so it can never drift from
the app's real role list. Badges render through the `role_label` helper, which
passes an unrecognised value through unchanged — sections saved before the
change still read correctly, with no migration.

## Help keys and coverage
`lib/help_keys.py` is the registry: every place in the app that should have an
article, grouped, as key and label. An article claims a key through
`help_key`, and claiming moves it — two articles on one key would make a "?"
ambiguous. The dashboard's Coverage panel lists the registered keys nothing has
claimed yet, each with a Write button that opens the new-article overlay with
the key already chosen. That list is the fill-day to-do list, generated from the
app rather than from memory.

This is a declared-contract seam: nothing in Python or the test suite notices a
page declaring a key that was never registered — it just renders a dead "?".
`tests/test_wiki_help_keys.py` scans every template for both `help_button('…')`
calls and literal `data-help-key` attributes, and fails on any key missing from
the registry.

## The contextual "?"
`help_button(key)` in `core/shared/templates/_shared_macros.html` puts a "?"
next to anything. `help_tray.js` loads from `base.html` and handles every click
by delegation, so it binds once and survives SPA swaps. The tray is the
`HelixTrays` shell from 2.5 with a third launcher — `HelixTrays.open()` needs a
pill for the panel's title, icon and open state, so the pill is load-bearing,
not decoration. Articles render through `_article_content.html`, the same
partial the reader uses.

Stacking was measured, not assumed: the tray panel is `z-index: 10000` against
the project overlay's 1000, and the dock sits at body level outside the
overlay's `backdrop-filter`, so the "?" works inside a project.

## Static
`wiki.js` (loaded by the wiki templates) and `wiki.css` (loaded globally by
`base.html`) are deferred to the shared-static pass and remain in `app/static`.

## Dependencies
core/shared only: `db` (extensions), the two wiki models, and `role_required`
(lib/decorators). No cross-module dependencies. Third-party: `nh3` for the
inline-HTML allowlist.

## Exports
The `wiki` blueprint.

## Tests
`tests/test_wiki_smoke.py` — the reader view requires authentication, the wiki
templates resolve through the module's `template_folder`, and video upload
gating, limits and NAS backup behave.
`tests/test_wiki_blocks.py` — every old block type converts and renders, and
the allowlist strips scripts.
`tests/test_wiki_editor.py` — the template carries every declared id and every
pinned library, and a save is cleaned: scripts stripped, unknown blocks
dropped, unsafe media URLs refused.
`tests/test_wiki_authoring.py` — every skeleton is a valid document that
survives the save cleaner, autosave creates a draft article and leaves the live
one untouched, and Save publishes and clears the draft.
`tests/test_wiki_dashboard.py` — the markup carries every declared id,
reordering writes list position without touching `updated_at`, creating seeds
the chosen skeleton at the end of its section, and reorder is admin-only.
`tests/test_wiki_help_keys.py` — every registered key is well-formed and
unique, no template names an unregistered key (it scans both `help_button('…')`
calls and literal `data-help-key` attributes), the coverage figures add up, and
claiming a key moves it off whichever article held it.
`tests/test_wiki_editor_access.py` — every `/wiki/editor` route plus the two
upload endpoints, read from the route baseline: a designer is refused, so is a
designer claiming to emulate an admin, and a real admin gets through whether or
not they are previewing as someone else.
`tests/test_wiki_help_tray.py` — the dock offers a Help launcher, the help
routes render an article or the gap, drafts read as a gap to a non-admin, and
only an admin is offered the write shortcut.
