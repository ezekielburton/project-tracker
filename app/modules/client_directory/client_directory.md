# client_directory

The Client Directory: a browse page of client companies and their contacts,
plus the two write endpoints used to create and update those records (the same
endpoints the project brief form posts to).

## Structure
```
app/modules/client_directory/
  routes/client_directory.py       # the `client_directory` blueprint
  templates/client_directory/      # index.html
  tests/test_client_directory_smoke.py
  client_directory.md
```

## Routes (the `client_directory` blueprint)
The blueprint carries `url_prefix='/directory/clients'`, so every route is
relative to it:
- `GET /directory/clients` — the directory page
- `POST /directory/clients/companies` — create or update a Client ("company"),
  keyed off whether the JSON body includes an `id`
- `POST /directory/clients/contacts` — create or update a Contact, same
  create-or-update pattern

## Data model
A **Client** is the company; **Contacts** hang directly off the Client model.
There is no separate Company model. Both `Client` and `Contact` live in
`core/shared/models`.

## Static
`css/client_directory.css`, `js/client_directory.js` — still served from the
global `/static` loader; move in the shared-static pass. The page is rendered
almost entirely client-side: the route hands the template a data blob and the
JS builds the list.

## Dependencies
- **core/shared**: `db` (extensions), `Client`/`Contact` (models),
  `role_required` (lib/decorators), `log_activity`/`get_actor` (lib/utils).
  All imported directly from core/shared.
- **No cross-module feature seams.** Only the app factory imports this module.
  The project brief form reaches the two write endpoints over HTTP (by URL),
  not by importing this module's code.

## Exports
The `client_directory` blueprint, registered in the app factory. The sidebar
links to `client_directory.index`.

## Tests
`tests/test_client_directory_smoke.py` — the directory page requires
authentication, and its template resolves. Uses the shared fixtures from
`core/shared`.
