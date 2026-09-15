# wiki

The internal wiki: browsing published sections and articles, and a full editor
for authors to create, edit, publish, and delete sections and articles
(including inline image and self-hosted video upload).

## Structure
```
app/modules/wiki/
  routes/wiki.py            # the `wiki` blueprint (wiki_bp)
  lib/blocks.py             # Editor.js document shape, conversion, sanitising
  static/js/wiki.js         # reader, dashboard CRUD, slug, publish/delete
  static/js/wiki_editor.js  # Editor.js setup for the article editor
  static/js/blocks/         # helix_callout.js, helix_video.js — our two tools
  templates/wiki/           # index, _article_content, editor_dashboard,
                            # editor_article, editor_section
  tests/test_wiki_smoke.py
  tests/test_wiki_blocks.py
  tests/test_wiki_editor.py
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
- `GET /wiki/editor` — the editor dashboard
- section + article CRUD under `/wiki/editor/...` (new, edit, save,
  toggle-publish, delete)

## Models
`WikiSection`, `WikiArticle`, from `core/shared`. Article content lives in
`sections_json` as an Editor.js document; `legacy_sections_json` holds the
pre-Editor.js content as a fallback.

## Content format
`lib/blocks.py` owns the block format: `load_blocks` parses stored content for
the renderer, `to_editorjs` converts the old block array, `clean_html` applies
the inline allowlist (nh3) to editor text, and `sanitize_document` cleans a
whole document on save — dropping unknown blocks and unsafe media URLs. Block
types: `paragraph`, `header`, `list`, `image`, `helixCallout`, `helixVideo`.

## Editor
`editor_article.html` mounts Editor.js, pinned by exact version and loaded from
jsDelivr: editorjs 2.30.7, header 2.8.9, list 1.9.0, image 2.10.3. `header` is
fixed to level 3, and `list` 1.x stores items as plain strings. Image and video
uploads reuse the existing endpoints — the image tool goes through an
`uploader.uploadByFile` hook so `/wiki/upload-image` keeps its response shape.
`wiki_editor.js` declares `TEMPLATE_CONTRACT`, the template ids it binds to;
`tests/test_wiki_editor.py` reads that list and checks the template.

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
