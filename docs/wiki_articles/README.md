# OVP wiki articles — source text

The master copy of every help article in the in-app wiki, one file per wiki section. Each article claims one help key from `app/modules/wiki/lib/help_keys.py`, and the "?" on that page opens it. A few articles (e.g. Light and dark mode) have no help key and are reached through search and their section.

| File | Wiki section | Articles |
|---|---|---|
| [getting-started.md](getting-started.md) | Getting started | 1–4, `core.roadmap`, 36–40 |
| [dashboard.md](dashboard.md) | Your dashboard | 5–6 |
| [projects.md](projects.md) | Projects | 7–15, 35 |
| [client-servicing.md](client-servicing.md) | Client Servicing | 16–20 (incl. 19a) |
| [digital-innovation.md](digital-innovation.md) | Digital Innovation | 21–24 |
| [hse.md](hse.md) | HSE & Compliance | 25–30 |
| [tools.md](tools.md) | Tools and directories | 31–34 |
| [wiki.md](wiki.md) | Using the wiki | `wiki.editor`, `wiki.help-keys` |
| [admin.md](admin.md) | Admin | 41 `admin.accounts` |

## How to use these files
- When a module changes, update its article here **and** in the wiki editor in the same release. A wrong article is worse than a missing one.
- Edit the block in place and bump its Status line. Don't keep old versions; git history has them.
- Block notation matches the editor's tools: `[Paragraph]`, `[Heading]`, `[List]` (one item per line), `[Callout]`.
- Style: short and scannable, lists over prose, one line of intro then straight into lists, roughly 150–250 words for a screen reference. Keep the gotchas, cut the reassurance. Each article ends with (or includes) one Callout: the thing people would otherwise ask about.
- Numbering follows registry order (`cs.accounts` is 19a, so 20–34 keep their numbers; Chat and Signal are 35–37; the wiki rework added 38–40).

## Wiki sections and relevant roles

| Section | Relevant roles |
|---|---|
| Getting started | (empty — everyone) |
| Your dashboard | (empty) |
| Projects | Designer, Team Lead, CS, Project Owner, Management |
| Client Servicing | CS, Finance, Management, Project Owner |
| Digital Innovation | Digital Innovation, Management |
| HSE & Compliance | HSE Officer, Management |
| Tools and directories | (empty) |
| Using the wiki | Admin |
| Admin | Admin |

Relevant roles is a relevance hint, never a lock: empty means everyone. It sorts the wiki: other roles' sections start folded in the rail and their search results sit last, dimmed. It never hides anything. In the wiki, 35 sits in Projects and 36–37 in Getting started.

## Open points
- **15 needs splitting.** `projects.notes` is now labelled "Site visits" and the chat drawer has its own "?" (`chat.projects`). Keep the Site visits half under 15; move the Chat half into 35.
- **1 had two open questions** when drafted: the name the team uses for the app (written as OVP), and whether "all work must be submitted in OVP first" still holds as stated. Confirm, then drop this line.
- **Missing text:** 2–10 were written in an earlier chat but never copied here. 25, 27, 28, 31–35 are still to write.
- **S1b (teams from deliverables)** changes 9, 10 and 11 — "Teams required" leaves the brief and Details tab; teams mark their part of a deliverable done.
- **36, 37 (Signal)** have no "?" button: the boards are built in the tray's JavaScript. They are reached from the Help browse list.
