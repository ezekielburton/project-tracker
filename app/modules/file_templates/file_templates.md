# file_templates

The C&CM File Templates library: a standalone (not project-specific) browse
page where users download per-store design template files (`.ai`), organized
Region → Customer → DeliverableType. Templates are small files kept on local
server disk, not the NAS.

## Structure
```
app/modules/file_templates/
  routes/file_templates.py   # the `file_templates` blueprint
  templates/file_templates/  # index.html
  tests/test_file_templates_smoke.py
  file_templates.md
```

## Routes (the `file_templates` blueprint)
- `GET /file-templates` — the browse page (Region → Customer → DeliverableType)
- `GET /file-templates/download/<deliverable_type_id>` — download one template
- `GET /file-templates/download-all/customer/<customer_id>` — zip a customer's
  templates
- `GET /file-templates/download-all/region/<region_key>` — zip a whole region's
  templates (each customer nested as a subfolder)
- `GET /file-templates/simulatin-files-link` — resolve the NAS Drive deep link
  for the shared Simulation Files folder

## Models
None of its own. Reads `Customer` and `DeliverableType` from
`core/shared/models`.

## Static
`css/file-templates.css`, `js/file-templates.js` — still served from the
global `/static` loader; move in the shared-static pass.

## Storage location
Uploaded template files live on server disk at `app/file_templates/` (created
on first upload; not in version control). The absolute path is resolved by the
shared helper `template_upload_folder()` in `core/shared/lib/paths`, anchored to
the Flask application root (`current_app.root_path`) so it is independent of
where any module file sits. This module reads from it; the admin upload route
writes to it — both use the one shared definition, so the location has a single
source of truth.

## Dependencies
- **core/shared**: `Customer`/`DeliverableType` (models), `build_zip`
  (lib/zip_utils), `build_drive_folder_url` (services/nas), and
  `template_upload_folder` (lib/paths). All imported directly from core/shared.
- **No cross-module feature seams.** This module depends only on core/shared.
  The admin panel depends on *it* only indirectly, through the shared
  `template_upload_folder` helper — not by importing this module.

## Exports
The `file_templates` blueprint, registered in the app factory. The sidebar
links to `file_templates.index`.

## Tests
`tests/test_file_templates_smoke.py` — the page requires authentication, the
template resolves, and `template_upload_folder()` resolves to
`<app_root>/file_templates` (guards the shared-path refactor).

## Notes
The endpoint `get_simulation_files_link` keeps its original misspelled URL
(`/file-templates/simulatin-files-link`) unchanged — renaming it would break
the front-end that calls it. Left as-is to preserve behaviour; a future,
deliberate rename is content/UX work, not part of this refactor.
