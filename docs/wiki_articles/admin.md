# Admin

### 41. `admin.accounts` — Accounts, departments and approvals

_Status: written 2026-10-05 for the org model; not yet pasted into the wiki._

```
Section: Admin

[Paragraph]
Accounts is where admins add people and set where they sit. Where someone sits decides what they can open in OVP and who approves their requests.

[Heading] The fields

[List]
Department - decides what the person can do in OVP
Job title - type it; the department's titles are suggested, and a new one is added to the list. It is only a label
Seniority - None, Manager, Head of Department or Management. Management adds the company-wide view
Reports to - their manager. Leave and other requests go to this person first
Team - Design only: 2D, 3D or Technical
Admin - full access to everything, including this panel

[Paragraph]
Project Owners hold everything Client Servicing can do, so they can step in when CS is stretched.

[Heading] Who approves a request

[List]
It goes up the Reports to chain
It stops at the first Management person, who approves too
Then any HR person signs it off
Management people go straight to HR

[Heading] Job titles

[List]
Rename a title for everyone who holds it
Hide a title to take it out of the suggestions; people keep it
Typing a hidden title brings it back

[Callout]
Set Reports to for everyone. Without it, a request goes straight to HR. A loop, two people reporting to each other, is refused when you save.
```
