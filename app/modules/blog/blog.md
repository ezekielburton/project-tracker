# blog

The internal blog / changelog: an admin-authored feed of posts that every
signed-in user can read and comment on. Posts are built from JSON "sections"
in an admin editor, published (optionally emailing everyone), and discussed in
threaded comments.

## Structure
```
app/modules/blog/
  routes/blog.py         # the `blog` blueprint
  templates/blog/        # index.html, _post_content.html, editor.html, v12_update.html
  tests/test_blog_smoke.py
  blog.md
```

## Routes (the `blog` blueprint)
Reader (any signed-in user):
- `GET /blog` — the post feed (admins also see unpublished drafts)
- `GET /blog/post/<id>` — one post's body + top-level comments (rendered fragment)
- `POST /blog/post/<id>/comments` — add a comment or threaded reply

Editor (admin only):
- `GET /blog/editor` — new-post editor
- `GET /blog/editor/<id>` — edit an existing post
- `POST /blog/posts` — create a post
- `PUT /blog/posts/<id>` — save a post (optionally email it to everyone)
- `POST /blog/posts/<id>/publish` — toggle publish (notifies on publish)
- `DELETE /blog/posts/<id>` — delete a post
- `DELETE /blog/comments/<id>` — delete a comment

Legacy:
- `GET /blog-post1-v1.2update` (`blog.v12_update`) — a single hardcoded
  release-notes page. See "Known debt".

## Models
None of its own. Uses `BlogPost` and `BlogComment` from `core/shared/models`
(a post stores its body as `sections_json`; comments self-reference via
`parent_id` for threading).

## Static
`css/blog.css`, `js/blog.js` — still served from the global `/static` loader,
not yet owned by the module. Moves in the shared-static pass.

## Dependencies
- **core/shared**: `db` (extensions), `BlogPost`/`BlogComment`/`User` (models),
  `get_actor` (lib/utils), and the `notify_all_of_new_blog_post` service
  (services/notifications). All imported directly from core/shared.
- **Cross-module (explicit, temporary):** `check_achievements` (achievements) —
  the gamification hook fired when a user comments. Imported from its current
  `app.achievements` path; it repoints when achievements migrates.

## Exports
The `blog` blueprint, registered in the app factory.

## Tests
`tests/test_blog_smoke.py` — the feed requires authentication, and the blog
templates resolve. Uses the shared fixtures from `core/shared`.

## Known debt
`v12_update.html` + `blog.v12_update` is a one-off "v1.2 release notes" page
hardcoded as a template instead of stored as a `BlogPost` row, and reached by a
literal URL (no `url_for`). The refactor moved it into the blog module — so the
module owns every blog URL and `core` no longer renders a blog template — but
did not change its behaviour. Converting it into a real post (or retiring it)
is future content work, deliberately out of the refactor's zero-behaviour-change
scope.
