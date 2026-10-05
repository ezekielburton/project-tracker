# Client Servicing

### 16. `cs.table` — The CS table, column by column

_Status: revised 2026-10-05: project owners can close projects too._

```
Section: Client Servicing

[Paragraph]
The CS table is the commercial view of every open job: dates, value, invoicing and who is on it. One line per job.

[Heading] The columns

[Paragraph]
They start in the order the weekly meeting runs, then the rest:

[List]

Project, Client, Status, CS Contact, Installation Date, Project Value (AED), LPO, Job No
Brief Date, Lead Designer(s), Client Approval, Project Owner, Client SPOC, Due Date
Scope, Store / Location, Removal Date, Invoice Month
Cost to Client (AED), Inward Cost (AED), Margin %, Priority

[Heading] The Project column

[List]

Always first, and stays in view when you scroll right
Click the project name to open it on the Projects page
The ⋯ beside the name opens Close project… (CS, project owners, management and admins)

[Heading] Quick filters

[List]

My jobs - jobs where you are the CS Contact or the Project Owner
Missing data - no installation date or no value
At risk - installs that will miss unless something changes
Installs this month

[Paragraph]
Each chip shows how many jobs it would leave. Chips combine, so My jobs plus Missing data is your own gaps. They work alongside the search box and the Filter panel. The Dashboard's "jobs need data" line opens this page with Missing data already on.

[Heading] Filter panel

[Paragraph]
Filter narrows by Client, CS Contact, Project Owner, Status, Scope or Priority. Clear all resets the panel and the search. The count under it says when you are looking at a filtered set.

[Heading] Making it yours

[List]

Drag a header edge to resize a column
Drag a header to reorder it. Project stays first
Click a header to sort. Blank values always go to the bottom, whichever direction you sort

[Paragraph]
Your widths and column order are saved to your account. Nobody else sees your layout.

[Heading] Editing in the table

[Paragraph]
Most fields are edited in place. Click the cell, change it, done. That covers Job No, CS Contact, Project Owner, Client SPOC, Scope, Store / Location, Priority, LPO, Invoice Month, the dates and the money fields.

[Paragraph]
A cancelled job leaves the rows and waits in the strip above the table until someone presses Close out.

[Callout]
A Status showing auto is worked out by the app from where the project actually is. Change it and you are overriding it, and it stops updating itself. Only override when the automatic answer is genuinely wrong.
```

### 17. `cs.dashboard` — The CS dashboard

_Status: revised 2026-09-30 for the CS polish pass (missing-data line, badge, one active set)._

```
Section: Client Servicing

[Paragraph]
The CS dashboard is the month at a glance: money, workload and what needs chasing.

[Heading] The panels

[List]

Urgent Actions - installs at risk or needing attention, plus invoices overdue, unbilled or missing an LPO. The red number counts these. Says "All clear" when there is nothing
Jobs need data - the line at the top of Urgent Actions. Counts jobs with no installation date or no value. Complete them opens the Table filtered to just those jobs
Next 7 Days - what is landing this week
Upcoming Installs - the next installs, coloured by risk
Invoicing Health - Pipeline, Confirmed and Invoiced for the month, plus invoiced as a share of confirmed
Stuck · No LPO - work that cannot be invoiced because the LPO is missing
CS Lead Workload - how the load is spread across CS
Status Spread - where everything sits
Active Projects and At Risk - the two headline counts

[Paragraph]
Active Projects counts the same jobs as the Table and Invoicing By Project. Cancelled jobs waiting to be closed out are not in it.

[Heading] Getting from here to there

[Paragraph]
Every row links to where it is fixed. The Calendar and Invoicing arrows take you straight to those pages with the same month in view.

[Callout]
Stuck · No LPO is the panel that costs money. A project sitting there is finished work that cannot be billed yet. Chase the LPO rather than waiting for month end.
```

### 18. `cs.calendar` — The CS calendar

_Status: written 2026-09-28_

```
Section: Client Servicing

[Paragraph]
The CS calendar plots projects by installation date, so you can see what is going out and when.

[Heading] Two views

[List]

Month - the grid. Click a day to see what is installing
Agenda - a flat list of the next 30 days

[Heading] The colours

[List]

On track / Ready
Attention - needs a look
At Risk - will miss unless something changes
Done / Closed

[Heading] What you can do from here

[List]

Click a day to open it
Click a project to see its owner, its next action and its quantity
Set qty on the spot without opening the project

[Callout]
The calendar only plots projects that have an installation date. A project with no date set will not appear anywhere on it, on any view. If something is missing from the calendar, check the date is filled in before assuming the calendar is wrong.
```

### 19. `cs.invoicing` — The invoicing tab

_Status: revised 2026-09-30 for the CS polish pass (active set, neutral band, export scope, cancelled jobs)._

```
Section: Client Servicing

[Paragraph]
Invoicing tracks what has been billed, what has not, and what is stuck.

[Heading] Two views

[List]

By Project - one row per open job. Cancelled jobs waiting to be closed out are not here, so the count matches the Dashboard
Monthly Summary - the month's totals. Closed and cancelled jobs still count in the month they belong to

[Heading] The columns

[List]

Client, Project, Project Value AED, Margin %
LPO / PO Number, LPO Date
Invoice No., Invoice Date, Invoice Amt AED, Inv. Month
GR · Validation
Days Pending

[Heading] Validation

[List]

Valid - good to go
Pending - waiting
No LPO - blocked, nothing can be billed
Overdue - past the threshold

[Paragraph]
No LPO and Overdue show in red. Nothing else in the table is flagged.

[Heading] Filtering and exporting

[List]

Filter by invoice month, or by validation state
Search matches project, client, LPO and invoice number as you type
Fill in the invoice number, date and amount straight in the row
Export downloads the current filters as a CSV. What you typed in search is not included

[Heading] Days Pending thresholds

[Paragraph]
Days Pending is how long an invoice has been waiting. The thresholds that turn it amber and then red are set in the Days Pending thresholds modal. Management and admins can change them. Everyone else sees the result.

[Heading] Cancelled jobs

[Paragraph]
Cancelled jobs leave By Project. CS closes them out from the Table's close-out strip, and one not yet invoiced then shows as Pending on Closed.

[Callout]
No LPO is not an invoicing problem, it is a chasing problem. Nothing in this tab will move that row until the LPO arrives.
```

### 19a. `cs.accounts` — Accounts

_Status: written 2026-10-01 for v2.6 (saved view, folded by default)._

```
Section: Client Servicing

[Paragraph]
Accounts lists every job, finished ones included, grouped by client or by CS lead. It replaces the CS Client and CS Contact sheets. Nothing is edited here.

[Heading] Choosing what you see

[List]

Group by - Client or CS lead
Client and CS lead - narrow the list to one
Billing month - All time, or one month
Search matches project, client and job number as you type

[Heading] The list

[List]

Each group shows its job count, its CS leads (or clients), and its Value and Invoiced totals
Groups run largest value first and start folded. Click a group's name to open or fold it, or use Expand all and Collapse all
Click a project to open it on the Projects page
+1 beside a project means a second CS is on it. Hover to see who. The job still counts once, under its lead
Cancelled jobs are listed with their status but never count as active

[Heading] CS load

[List]

One row per CS lead for the billing month: Jobs, Active, Invoiced, No LPO
Active - not invoiced and not cancelled
No LPO - no LPO recorded yet, the same rule as Stuck on Invoicing
Value and invoiced amount sit under each name, with a Total at the bottom

[Paragraph]
The load panel follows the billing month only. The Client and CS lead filters do not change it.

[Paragraph]
Accounts remembers your last Group by and which groups you left open, on any device.

[Paragraph]
Everyone who can open Client Servicing sees every figure here.

[Callout]
A job's billing month is its invoice date, else its invoice month, else its removal date. That is the Monthly Summary's rule, so a month's value here matches its Pipeline there. A job with none of those dates only shows under All time.
```

### 20. `cs.closed` — Closed projects

_Status: revised 2026-10-05: project owners can close projects too._

```
Section: Client Servicing

[Paragraph]
Closing a project takes it off the active list. Closed projects stay searchable and keep their numbers.

[Heading] Closing a live job

[List]

On the Table, press ⋯ beside the project name
Choose Close project…
Confirm

[Heading] Closing out a cancelled job

[List]

Cancelled jobs wait in the strip above the Table
Press Close out
Answer whether it needs invoicing
If it does, say whether it has been invoiced yet. Yes asks for the real invoice date

[Heading] Invoice state

[List]

Not needed - no invoice for this one
Pending - needs invoicing, not done yet
Invoiced - billed

[Paragraph]
A project closed as Pending can be marked invoiced later from this page. You do not have to reopen it.

[Heading] Finding a closed project

[List]

Filter by year, quarter or month
Each row shows Client, Project, Value AED, Closed date, Closed by and Invoice state

[Heading] Who can close

[Paragraph]
CS, project owners, management and admins.

[Callout]
Closing is not deleting. The project keeps its history, its files and its value, and it still counts in the month it closed in. Closing is final, so a closed project cannot be reopened.
```
