# wiki

The internal wiki: a reader on the shared module rail (home, search, one page
per article), the contextual "?" Help tray, and a full editor for authors to
create, edit, publish and delete sections and articles (including inline image
and self-hosted video upload).

## Structure
```
app/modules/wiki/
  routes/wiki.py            # the `wiki` blueprint (wiki_bp)
  lib/blocks.py             # Editor.js document shape, conversion, sanitising,
                            # plain text for search, video length
  lib/article_templates.py  # the How-to / Reference / Blank skeletons
  lib/help_keys.py          # the help-key registry and coverage figures
  lib/search.py             # full-text search and highlighted snippets
  lib/search_misses.py      # searches that found nothing; the Write next list
  lib/relevance.py          # role relevance: scope, collapsed and dimmed sections
  lib/reader.py             # rail items, Start here, Recently updated, Related
  lib/freshness.py          # "Reviewed this quarter" and Review due
  lib/views.py              # read counts and Most read
  lib/votes.py              # the "Useful?" answers and the Not useful list
  lib/uploads.py            # where uploads live; finding and deleting unused ones
  static/css/wiki.css       # loaded globally by base.html (the tray uses it too)
  static/js/wiki_reader.js  # reader pages: fill height, legacy #article-N links
  static/js/wiki.js         # editor dashboard buttons: slug, publish, delete
  static/js/wiki_editor.js  # Editor.js setup for the article editor
  static/js/block_drag.js   # capture-phase block dragging inside the editor
  static/js/editor_autosave.js
  static/js/editor_dashboard.js
  static/js/help_tray.js    # loaded by base.html, not by the wiki templates
  static/js/blocks/         # helix_callout.js, helix_video.js — our two tools
  templates/wiki/           # index, article, search, _rail, _macros,
                            # _article_content, editor_dashboard,
                            # editor_article, _section_modal, _article_modal,
                            # _coverage_panel, _write_next_panel,
                            # _help_article, _help_empty, _help_browse
  tests/                    # see Tests
  wiki.md
```

## Routes (the `wiki` blueprint)
Reader (any signed-in user):
- `GET /wiki` — home: search box, Start here for the reader's role, Recently
  updated and Most read this month
- `GET /wiki/article/<id>` — one article as its own page. Drafts are 403 unless
  the effective user can `manage_wiki`
- `POST /wiki/article/<id>/vote` — the reader's own "Useful?" answer. 403 on a
  draft and for anyone who manages the wiki, emulating or not
- `GET /wiki/search?q=` — results with highlighted snippets; a search that
  finds nothing is recorded (see Search misses)
- `POST /wiki/search/miss/<id>/note` — "What were you trying to do?" on a miss.
  Only the person who searched can add it; anyone else gets 404
- `GET /wiki/help`, `GET /wiki/help/<key>`, `GET /wiki/help/article/<id>` — the
  Help tray: browse list, the article claiming a key (or the gap plus a "Write
  this article" shortcut for admins), and an article picked from the list

Editor (`@require('manage_wiki', real_user=True)` — emulating never grants it):
- `GET /wiki/editor` — the dashboard; `?help_key=` opens the new-article
  overlay with that key already chosen
- `POST /wiki/upload-image`, `POST /wiki/upload-video` — inline image upload,
  and self-hosted video (mp4/webm, 200MB cap) saved local-first under
  `upload_root()/videos/` and backed up to `/Admin/OVP/Wiki` on a background
  thread. The Video block toggles between Embed URL and Upload File
  (`block.source`)
- `POST /wiki/editor/article/create` — seeds the chosen skeleton, records the
  author, redirects into the editor
- `POST /wiki/editor/article/save` — makes the working copy live, rebuilds
  `search_text`, sets `updated_by_id`, and counts as a review (`reviewed_at`)
- `POST /wiki/editor/article/autosave` — parks the working copy in the
  article's draft; creates the article first if it does not exist yet.
  `updated_at` is assigned to itself, so the reader's Updated line never moves
- `POST /wiki/editor/article/<id>/reviewed` — Reviewed button: sets
  `reviewed_at` without touching `updated_at`
- `POST /wiki/editor/misses/dismiss` — drops a phrase from Write next
- `POST /wiki/editor/uploads/clean` — deletes unused uploads (see Uploads)
- `POST /wiki/editor/sections/reorder`, `POST /wiki/editor/articles/reorder` —
  each takes an ordered list of ids and writes `sort_order` from list position
- the rest of article CRUD (edit, toggle-publish, delete) and
  `POST /wiki/editor/section/save` plus section toggle-publish and delete

## Models
From `core/shared/models/wiki.py`:
- `WikiSection`, `WikiArticle`. Article content lives in `sections_json` as an
  Editor.js document; `draft_sections_json` holds the autosaved working copy
  (cleared when Save makes it live) and `legacy_sections_json` the
  pre-Editor.js content. `help_key` names the page an article explains.
  `created_by_id` / `updated_by_id` (users, SET NULL) and `reviewed_at` drive
  the byline. `search_text` is plain text rebuilt on every save;
  `search_vector` is a STORED generated `tsvector` over title (weight A) and
  `search_text` (weight B), with a GIN index. Both are `deferred`, so ordinary
  article queries never load them
- `WikiSearchMiss` — a search that found nothing: phrase, `phrase_key`
  (stemmed words), user, optional note, `dismissed_at`
- `WikiArticleView` — one read: article, user, source (`page` or `tray`)
- `WikiArticleVote` — one "Useful?" answer per user per article, with the
  "What was missing?" note on a no

Migrations: `add_wiki_search`, `add_wiki_search_misses`, `add_wiki_authorship`
(credits every existing article to the owner's account), `add_wiki_views`,
`add_wiki_votes`.

## Content format
`lib/blocks.py` owns the block format: `load_blocks` parses stored content for
the renderer, `to_editorjs` converts the old block array, `clean_html` applies
the inline allowlist (nh3) to editor text, and `sanitize_document` cleans a
whole document on save — dropping unknown blocks and unsafe media URLs. Block
types: `paragraph`, `header`, `list`, `image`, `helixCallout`, `helixVideo`.
`document_text` turns a document into the plain text that search indexes.

Video embeds are host-checked, not substring-matched: `EMBED_HOSTS` allows
youtube.com, youtu.be and vimeo.com, matched against the parsed hostname, and
anything else renders as a plain link. `load_blocks` re-checks on read, so
content migrated in before the save gate existed is judged too.

A `helixVideo` block carries an optional `length` in seconds (1–3600). The
editor fills it from an uploaded file and lets the author type it for an
embed. `lead_with_video` moves the first video to the top when an article is
read; `format_length` prints it as `40s`, `1m 20s`, `2m`.

## Reader
Every reader page sits on the shared `module_rail` (Home, Search, then one
group per section), with the role scope toggle under Search through the
macro's `caller_after`. `wiki_reader.js` declares `TEMPLATE_CONTRACT` and runs
`watchFillHeight` on the reader and the rail. Old `/wiki#article-N` links are
forwarded to the article page.

The article page leads with the video, then the written steps. The byline
reads "Updated … by … · Reviewed this quarter · N reads". The side column has
the "?", Edit for wiki managers, On this page (one link per heading) and
Related (three from the same section). The tray's "Open full article" lands
here.

Home: Start here is automatic — the first three articles of the first
everyone section, plus the first three of the first section for the reader's
role, each with its video length. Recently updated lists five; Most read this
month lists five.

## Role relevance
Relevance, not permission: nothing is hidden and no `can()` check is involved.
A section's Relevant roles are stored as role keys from `ROLE_LABELS`; old
label values (e.g. "CS") resolve case-insensitively through
`relevance._KEY_BY_NAME`, so no migration was needed. Empty means everyone.

- Scope is `mine` (the reader's own role) or `all`. The default is `mine`;
  wiki managers default to `all`
- In `mine`, other roles' sections start collapsed on the rail (the current
  article's section always opens) and their search results sit last and dimmed
  with a "for …" tag
- `scope_param` carries `?scope=` in links only when it differs from the
  reader's default, so emulating a role picks up that role's view straight away
- The rail's `multi_open` and per-item `open` opt-ins keep several sections
  open at once

## Search
`lib/search.py` — `websearch_to_tsquery('english', …)` against
`search_vector`, ranked by `ts_rank` (title weighted above body), with `ts_headline`
snippets. Snippet markers are control characters, the text is escaped, then
the markers become `<mark>`, so article text can never inject HTML. Drafts are
searched only for wiki managers. Results show "Searched N articles".

## Search misses and Write next
A search that finds nothing is recorded once per person per phrase per day
(wiki managers' searches are not recorded). The page offers "What were you
trying to do?" and, when others asked the same, "Asked N times this month by M
people". Phrases are grouped by their stemmed words, so "approving" and
"approve" count together.

The dashboard's Write next panel lists phrases that still find nothing, most
asked first, with notes, a Write button (opens the new-article overlay with
the phrase as the title) and Dismiss. Beneath it, Not useful lists articles
with "no" answers since their last update, with the notes.

## Reads and "Useful?"
A read counts once per person per article per day, from the page or the tray.
Wiki managers' reads and votes never count, even while emulating. A yes clears
any earlier note; a no keeps "What was missing?" (500 characters). Saving the
article clears its Not useful entry, because only noes after `updated_at`
count.

## Freshness
`reviewed_at` is set by Save and by the dashboard's Reviewed button. The
byline says "Reviewed this quarter" or the month it was last reviewed; the
dashboard shows Review due on any article not reviewed this calendar quarter.

## Uploads
`upload_root()` is `WIKI_UPLOAD_ROOT` when set (tests use a temp folder), else
`app/static/wiki-uploads`. `unused_uploads()` lists files in the root and
`videos/` that no live, draft or legacy content names and that are older than
24 hours. Clean up on the dashboard deletes them and removes the NAS backup of
each video in the background.

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
article when it is created. Saving and publishing are one action: a Published
tick box posts with the form, and the save clears the draft. Slugs are derived
from the title on create and never change afterwards, so links to an article
keep working.

## Editor dashboard
Sections and their articles are reordered by dragging (Sortable.js, loaded
globally by `base.html`), and the order saves on drop — `sort_order` is never
typed. Section metadata and new articles are handled in overlays on the
dashboard using the app's standard modal (`.modal-overlay` / `.modal-box`, plus
`.wiki-modal` for the wiki's own spacing), so there are no separate form pages.
`editor_dashboard.js` declares `TEMPLATE_CONTRACT`, the ids it binds to across
the templates; `tests/test_wiki_dashboard.py` reads that list and checks the
markup. The side column holds Coverage, Write next / Not useful, and the
Unused uploads line with Clean up.

A section's Relevant roles picker is built from `ROLE_LABELS` in
`core/shared/lib/capabilities.py` so it can never drift from the app's real
role list. Badges render through the `role_label` helper.

## Help keys and coverage
`lib/help_keys.py` is the registry: every place in the app that should have an
article, grouped, as key and label. An article claims a key through
`help_key`, and claiming moves it — two articles on one key would make a "?"
ambiguous. The dashboard's Coverage panel lists the registered keys nothing has
claimed yet, each with a Write button that opens the new-article overlay with
the key already chosen.

This is a declared-contract seam: nothing in Python or the test suite notices a
page declaring a key that was never registered — it just renders a dead "?".
`tests/test_wiki_help_keys.py` scans every template for both `help_button('…')`
calls and literal `data-help-key` attributes, and fails on any key missing from
the registry.

## The contextual "?"
`help_button(key)` in `core/shared/templates/_shared_macros.html` puts a "?"
next to anything. `help_tray.js` loads from `base.html` and handles every click
by delegation, so it binds once and survives SPA swaps. The tray is the
`HelixTrays` shell with a third launcher — `HelixTrays.open()` needs a pill for
the panel's title, icon and open state, so the pill is load-bearing, not
decoration. Articles render through `_article_content.html`, the same partial
the article page uses, with the video first.

Stacking was measured, not assumed: the tray panel is `z-index: 10000` against
the project overlay's 1000, and the dock sits at body level outside the
overlay's `backdrop-filter`, so the "?" works inside a project.

## Dependencies
core/shared only: `db` (extensions), the wiki models, `can` / `require` /
`effective_user` (lib/capabilities), `slugify`, the `module_rail` and
`help_button` macros, and the NAS client for video backup. No cross-module
dependencies. Third-party: `nh3` for the inline-HTML allowlist. Postgres
full-text search; no search library.

## Exports
The `wiki` blueprint.

## Tests
- `test_wiki_smoke.py` — the reader requires authentication, templates
  resolve, and video upload gating, limits and NAS backup behave
- `test_wiki_blocks.py` — every old block type converts and renders, and the
  allowlist strips scripts
- `test_wiki_editor.py` — the template carries every declared id and pinned
  library; a save is cleaned
- `test_wiki_authoring.py` — skeletons survive the cleaner, autosave creates a
  draft and leaves the live article alone, Save publishes and clears the draft
- `test_wiki_dashboard.py` — declared ids, reordering, creating, admin-only
- `test_wiki_help_keys.py` — the registry is well-formed, no template names an
  unregistered key, coverage adds up, claiming moves a key
- `test_wiki_editor_access.py` — every `/wiki/editor` route plus the uploads,
  from the route baseline: designers refused, emulation never grants access
- `test_wiki_help_tray.py` — the tray renders an article or the gap; drafts
  read as a gap to a non-admin
- `test_wiki_search.py` — a body-only word finds the article, other forms of
  a word match, a title match outranks a body match, snippets are escaped
  before marking, save rebuilds the index and autosave doesn't, drafts only for
  managers (and not while they emulate), one query however many results
- `test_wiki_search_misses.py` — a miss is recorded once a person a day,
  wordings of one question share a key, answered and old questions drop off,
  dismiss, notes are the searcher's own, managers' searches not recorded
- `test_wiki_authorship.py` — create and save set the byline, autosave records
  nobody, Reviewed leaves Updated alone, the quarter rule, Review due
- `test_wiki_relevance.py` — keys and old label values resolve, role filtering
  hides nothing, other roles collapse and dim only while scoped, managers
  default to Everything, emulation lands on the emulated reader's default
- `test_wiki_reader.py` — home, article page and rail, the reader template
  contract, On this page, Related, Start here, Recently updated, empty sections
  left off, old hash links forwarded, the tray opens the article page
- `test_wiki_video.py` — length is bounded on save and on read, the first video
  leads in the reader and the tray, lengths print correctly
- `test_wiki_views.py` — a read counts once a day from page or tray, managers
  don't count, Most read ranks the month in one query
- `test_wiki_votes.py` — one changeable answer per person, managers and drafts
  refused, a no asks what was missing, Not useful clears on save, one query
- `test_wiki_uploads.py` — referenced and recent files are kept, only the two
  upload folders are looked at, Clean up deletes local files and NAS backups
  and survives a NAS failure (the endpoint's gate is covered by
  `test_wiki_editor_access.py`)
