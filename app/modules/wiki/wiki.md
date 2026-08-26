# wiki

The internal wiki: browsing published sections and articles, and a full editor
for authors to create, edit, publish, and delete sections and articles
(including inline image upload).

## Structure
```
app/modules/wiki/
  routes/wiki.py            # the `wiki` blueprint (wiki_bp)
  templates/wiki/           # index, _article_content, editor_dashboard,
                            # editor_article, editor_section
  tests/test_wiki_smoke.py
  wiki.md
```

## Routes (the `wiki` blueprint)
- `GET /wiki` — the reader view (published sections/articles)
- `GET /wiki/article/<id>` — one article's content
- `POST /wiki/upload-image` — inline image upload for the editor
- `GET /wiki/editor` — the editor dashboard
- section + article CRUD under `/wiki/editor/...` (new, edit, save,
  toggle-publish, delete)

## Models
`WikiSection`, `WikiArticle`, from `core/shared`.

## Static
`wiki.js` (loaded by the wiki templates) and `wiki.css` (loaded globally by
`base.html`) are deferred to the shared-static pass and remain in `app/static`.

## Dependencies
core/shared only: `db` (extensions), the two wiki models, and `role_required`
(lib/decorators). No cross-module dependencies.

## Exports
The `wiki` blueprint.

## Tests
`tests/test_wiki_smoke.py` — the reader view requires authentication, and the
wiki templates resolve through the module's `template_folder`.
