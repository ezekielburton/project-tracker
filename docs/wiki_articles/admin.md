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

### 42. `dashboard.admin` — The admin system pages

_Status: new for 2.7; not yet pasted into the wiki._

```
Section: Admin

[Paragraph]
The Admin dashboard shows how OVP itself is running. Only admins see it, and it stays yours while you view the app as someone else.

[Heading] The pages

[List]
Overview - status strip, Needs attention, today's use, next jobs
System - uptime, CPU, memory, temperature, storage, network, updates
Database - size, connections, largest tables, slowest queries, upkeep
Performance - response times, error rate, page load by module, slowest routes, workers
Usage - who is on, actions by day, module and hour, logins, the emulation log
Errors - errors grouped by cause, 500s by route, the raw log
Uptime - 30 days at a glance, deploys, incident notes
Jobs - every scheduled job and Run now (its own article)

[Heading] Reading it

[List]
The badge at the top reads Live while the data is fresh, otherwise how long since it updated
Cards refresh on their own; there is nothing to reload
Needs attention lists only what is wrong, and hides when all is well
Hover a chart for exact values
Click an error group to see its log lines
No data means the server hasn't sent that reading yet
A number on Errors or Jobs in the menu counts new error groups (24 hours) or failed jobs (7 days)

[Heading] Incident notes

[List]
On Uptime, add what happened, the date, the minutes down and a note
A restart within 15 minutes of a deploy is marked planned without a note

[Callout]
Badge stuck on "Updated N min ago"? The snapshot job has stopped. Check it on Jobs.
```

### 43. `dashboard.jobs` — Admin jobs and Run now

_Status: new for 2.7; not yet pasted into the wiki._

```
Section: Admin

[Paragraph]
Jobs lists every task the server runs on a timer: backups, checks and clean-ups. Every run is recorded here.

[Heading] The table

[List]
Schedule - when it runs, in Dubai time
Last run - when it last finished, and how long it took
Result - ok or failed
Next run - when it runs next
Heartbeat reads "timer only": it runs every minute and can't be started by hand

[Heading] Run now

[List]
Press Run now; it turns to Confirm. Press again within 4 seconds
The job starts on the server within seconds, and its row updates when it finishes
A job never runs twice at once, so a manual run waits for a timed one
Every Run now goes in the activity log with your name

[Heading] The jobs

[List]
Nightly backup, 23:00 - a copy on the server and one on the NAS
Weekly restore test, Sundays - proves the newest backup restores
Orphaned uploads check - lists old files no project uses; deletes nothing
Snapshot collector, every minute - feeds every admin page
VACUUM ANALYZE, data retention, the notifications purge and the preview-cache cleanup keep things tidy

[Callout]
A failed backup or restore test also shows on the Overview under Needs attention. Fix the cause, then Run now to clear it.
```
