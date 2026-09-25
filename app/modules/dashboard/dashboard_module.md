# Dashboard module

**What it is.** The page people land on after logging in. It shows each person what needs them: their work, what is late, and what is waiting on someone else. Every role sees its own version.

**Who it is for.** Admin, Management, Design Team Leads, Designers, Client Servicing and Project Owners. The HSE officer has their own module and does not use this one.

## Where it is heading (the 2.6 rework)
Each role gets a side menu (the rail) inside the module. The first page is always **Overview**; the other pages depend on the role. Every rail ends with a greyed **My hub · Soon** slot, kept for the future HR module (leave, reimbursements, payslips).

| Role | Rail pages |
|---|---|
| Admin | Overview · System · Database · Performance · Usage · Errors · Uptime · Jobs |
| Management | Overview · Escalations · Delivery · Teams · Clients · Adoption |
| Design Team Lead | Overview · Assignments · Team · Calendar |
| Designer | Overview · My projects · Site visits · Calendar |
| Client Servicing | Overview · Approvals · My clients · Calendar |
| Project Owner | Overview · Approvals · My projects · Site visits · Calendar |

A number on a rail entry counts the things on that page that need the person. No number means nothing needs them.

**Shared across every dashboard:**
- **Escalations** — raised from a project, decided by management. Each Overview shows the ones you raised.
- **Nudges** — one reminder button everywhere (Remind / Nudge), delivered as a notification.
- **Site visits** — logged on a project, shown on every calendar.
- **Calendar** — one shared page; each role sees its own events.

Admin sees another role's dashboard by viewing as that person, not through extra menu entries.

## How it gets its data
When a dashboard page loads, it asks for the person's projects **once**, together with everything the cards need about them: deliverables, customers, designers, flags, status history. Every card then reads from that one list.

Before this, each card asked on its own, then asked again for every single project. An admin page made about 1,500 database requests; it now makes about 50 and loads about seven times faster. The numbers on the page did not change.

**Rules for anyone adding to the dashboard:**
- New cards take their projects from `lib/project_loader.py`. They never ask the database for projects themselves.
- Which projects a role can see is decided in one place: `scope_query()` in that file.
- The list is for showing things. A page that changes a project must not rely on it afterwards.
- One number, one source. A count shown in two places must come from the same list, or the page ends up saying "11 overdue" here and "7 overdue" there.

**Checks:**
- `tests/test_dashboard_perf.py` fails if a page's database requests grow as projects are added.
- `refactor/dashboard_snapshot.py` saves every card's output so a change can be compared before and after (`save before`, `save after`, `diff before after`).

## Files
```
app/modules/dashboard/
  routes/dashboard.py     the pages and the data behind each card
  lib/project_loader.py   the one project fetch per page load (who sees what, loaded once)
  lib/dashboard_logic.py  small rules: deadline colour, clashes, whose turn it is
  templates/              one page per role, plus the shared cards
  static/                 the module's CSS and JS
  tests/
```

## Things to know
- **Internal name.** The module is registered under the name `projects`, not `dashboard`, for historical reasons. Links use `projects.index`. Do not rename it.
- **Access.** Every page and every data address behind it needs the `view_workspace` permission. New role pages get their own permission from the capabilities map, never a check on the role name.
- **Borrowed piece.** The average-project-time figure comes from the time tracking module.
- **Help keys.** Each role's page declares one for the wiki, e.g. `dashboard.designer`.

## Build progress
The rework runs in 14 steps, one chat each. The full plan is `dashboard_master_plan.md` in the OVP project docs.

| Step | What | Status |
|---|---|---|
| S1 | Faster, consistent data loading | Done |
| S2 | Shared shell, role rail, rail counts, calendar frame | Next |
| S3 | Escalations | — |
| S4 | Nudges | — |
| S5 | Site visits | — |
| S6 | Shared calendar page | — |
| S7–S8 | Admin data collection and admin pages | — |
| S9 | Management dashboard | — |
| S10 | Design Team Lead dashboard | — |
| S11 | Designer dashboard | — |
| S12 | Client Servicing dashboard | — |
| S13 | Project Owner dashboard | — |
| S14 | Adoption page | — |

This file replaces `dashboard.md`, which is removed in the last step.
