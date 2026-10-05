# Digital Innovation

### 21. `di.board` — The DI board

_Status: draft 2026-09-28, awaiting approval_

```
Section: Digital Innovation

[Paragraph]
The DI board is where Digital Innovation's work lives. One board per project, one card per feature, moving left to right through eight stages.

[Heading] The stages

[List]

Researching
Planning
Coding
Testing
Optimizing
Management Review - reads Client Review on an External project
Revision
Implementation

[Heading] Working a feature

[List]

Click a card to open it
Tick steps off as you go. Add a step if this job needs one the defaults don't have
Move to stage sends it to any stage, forward or back
Close this feature once every Implementation step is done

[Paragraph]
Going back to a stage picks up the steps you left there. The first time a feature reaches a stage, it starts with that stage's default steps.

[Heading] Projects

[List]

The OVP board is permanent. Everyone can see it and it can't be closed
Other boards are visible to admins and management
+ New project asks for a name and a track: Internal or External
Link to project connects the board to its project in OVP
The × next to a project in the rail closes it and moves it to the Archive

[Heading] Incoming

[Paragraph]
On the OVP board only. Incoming lists ideas people have sent in through Signal. Promote turns one into a card and tells the person who sent it. Dismiss hides it from the tray and leaves the request itself alone.

[Heading] Closed features

[Paragraph]
The strip under the columns lists finished features with the date they closed. Reopen puts a feature back in Implementation with its steps as they were.

[Callout]
Moving a card never checks its steps. The one gate is closing: a feature only closes once its Implementation steps are all done. Changes to the board are admin-only for now; everyone else can view.
```

### 22. `di.templates` — DI templates

_Status: draft 2026-09-28, awaiting approval_

```
Section: Digital Innovation

[Paragraph]
Edit Templates sets the default steps each stage starts with, for every DI project.

[Heading] Editing the defaults

[List]

+ Add step - a title, plus optional details
The arrows move a step up or down
Edit changes a step's wording
× deletes it

[Heading] When the defaults are used

[Paragraph]
A feature picks up a stage's defaults the first time it enters that stage. From then on the steps belong to the feature and can be changed there.

[Heading] Who can edit

[Paragraph]
Admins.

[Callout]
Editing a template never changes a feature that already has its steps. Only features reaching that stage for the first time get the new list. To fix a feature already in progress, edit its steps on the card.
```

### 23. `di.performance` — DI performance

_Status: draft 2026-09-28, awaiting approval_

```
Section: Digital Innovation

[Paragraph]
Performance shows what each DI project has cost, what it is charged at, and the profit in between.

[Heading] Choosing a period

[List]

Weekly, Monthly or Quarterly
The arrows step back and forward a period
A project shows in any period it was active during

[Heading] The table

[List]

Project, Status
Dev time - hours logged
Cost - everything logged in the period
Charge - what the client pays
Profit - charge minus cost
Expand a project to see its features

[Paragraph]
The headline figure is charge minus costs so far, across open projects. Export gives you the current view as an Excel file.

[Heading] Where the numbers come from

[Paragraph]
Costs are logged in Cost breakdown on each board:

[List]

Dev Time - hours against a feature, priced at the department's hourly rate
Claude, Hardware, Licensing - project-level costs
Client charge - set once per project, which gives the projected profit
Entries can be deleted but not edited. To correct one, delete it and add it again

[Paragraph]
The hourly rate and currency live in Settings. A new rate only prices Dev Time logged after the change. Older entries keep the rate they were saved with.

[Heading] Who can see it

[Paragraph]
Admins and management.

[Callout]
Weeks are always live. A month or quarter locks its numbers the first time anyone views it after it ends. Log costs before month end, because a cost added after the month has locked won't change that month's figures.
```

### 24. `di.archive` — The DI archive

_Status: draft 2026-09-28, awaiting approval_

```
Section: Digital Innovation

[Paragraph]
The Archive holds DI projects that are no longer active. Nothing in here is lost, and any of them can come back.

[Heading] Two lists

[List]

Closed - projects taken off the rail. Reopen it, or Archive it
Archived - tucked away further. Reopen it

[Paragraph]
Reopen puts a project back on the rail with its features, steps and costs as they were.

[Heading] Closing a project

[Paragraph]
Press the × next to the project in the rail. The OVP board is permanent and can't be closed.

[Callout]
Closing a project is not deleting it. Its features, steps and cost history all stay, and it still counts in Performance for the periods it was active.
```
