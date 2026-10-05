# Projects

### 7. `projects.table` — Reading the projects table

_Status: not in this file yet_

### 8. `projects.filters` — Filtering and sorting

_Status: not in this file yet_

### 9. `projects.create` — Starting a project

_Status: not in this file yet. S1b removes "Teams required" from the brief._

### 10. `projects.details` — The Details tab

_Status: not in this file yet. S1b removes "Teams required" from the Details tab._

### 11. `projects.deliverables` — The Deliverables tab

_Status: written (earlier chat). Update for S1b: teams come from deliverables; each team marks its part done._

```
Section: Projects

[Paragraph]
Deliverables is the list of things to actually make, and who is making each one.

[Heading] The columns

[List]

Name
Deadline
Assignments - which designer is on it
Status
Revisions - how many rounds it has been through
Reference - files for that specific deliverable

[Heading] Focused and All

[List]

Focused - only the deliverables you are assigned to
All - everything on the project

[Paragraph]
Designers and team leads land on Focused. Everyone else lands on All.

[Heading] Assigning work

[List]

Admins, management and CS can assign anyone
Designers and team leads can assign themselves only

[Callout]
A designer picking someone else's name gets refused. This is not a bug. If work needs moving to another person, ask CS or a lead to do it.

[Heading] Editing the list

[Paragraph]
Edit Deliverables opens the list for changes - add, rename, re-date, cancel. C&CM projects work the same way but the deliverables sit under each customer.

[Heading] Skipping to Pre-Production

[Paragraph]
Confirm Skip sends a deliverable straight past design to Pre-Production. Use it when there is nothing to design. Production Only projects do this to everything automatically at creation.
```

### 12. `projects.submissions` — Submitting a draft for review

_Status: written (earlier chat)_

```
Section: Projects

[Paragraph]
Submissions is where design work goes out for approval and comes back with feedback.

[Heading] The flow

[List]

Designer builds a draft and adds files to it
Designer ticks which files to include, adds a note for CS, and sends it
CS reviews it and either submits it to the client, asks for an internal revision, or approves it
Client feedback comes back as a client revision, which starts the next round

[Heading] Who does what

[List]

Designers and team leads - create drafts, add files, send for review
CS, management and admins - Submit to Client, Request Client Revision, Flag Internal Revision, Mark Approved

[Heading] The draft card

[List]

Concept / Draft / Current - which stage the work is at
Include in this Submission - tick the files that go out. Anything unticked stays in the draft
Note for CS - optional, but the fastest way to stop a pointless revision round
Preview, Download, Remove - per file
History - every round, with the note from whoever sent it

[Callout]
Submissions will not open on a project that still says Briefed. Someone has to press Start Project on the Details tab first. Projects that already had a submission before this rule came in still work.
```

### 13. `projects.preproduction` — Pre-production

_Status: written (earlier chat)_

```
Section: Projects

[Paragraph]
Pre-production is the check before a deliverable goes to production. Each deliverable is checked per stream.

[Heading] The streams

[List]

2D
3D
Technical

[Paragraph]
A deliverable only shows the streams it actually needs.

[Heading] What you do here

[List]

Assign someone to a stream
Approve a stream once it is checked
Flag a stream back to the designer, with a comment
CS Note - the note carried over from client approval
History - every flag and approval on that deliverable

[Heading] Active and All deliverables

[List]

Active - what is in pre-production now
All deliverables - everything on the project

[Heading] Who can do what

[List]

Approve or flag - admins, management, the CS Lead, the Project Owner
Mark a stream done - designers, team leads, management, admins
Skip to Pre-Production - admins, management, the CS Lead, Secondary CS, the Project Owner

[Callout]
A flagged stream goes back to having no status, which looks identical to never started. The app tells them apart by the flag history, so a stream showing a flag comment is waiting on a reupload, not waiting to begin.
```

### 14. `projects.flags` — Raising a flag

_Status: written (earlier chat)_

```
Section: Projects

[Paragraph]
A flag says the brief is unclear or something is blocking the work. It notifies CS and puts the project on the Decisions Needed card.

[Heading] The four kinds

[List]

Project - something about the brief as a whole
Deliverable - one specific deliverable. You have to pick which one
Concept - the concept work
KV - the key visual

[Heading] Raising one

[List]

Open the project, go to the flag panel
Pick the kind
Write what is wrong. A message is required, an empty flag is refused
Send

[Paragraph]
CS is notified straight away, and the project appears on Decisions Needed with a day counter running.

[Heading] Replying and resolving

[List]

Anyone who can raise flags can reply to one, so a flag becomes a thread
Mark Resolved is for the person who raised it. Nobody else can close your flag

[Callout]
Only the person who raised a flag can resolve it. If your question was answered elsewhere, go back and close it yourself. An unresolved flag keeps counting days on someone's dashboard.

[Heading] Who can raise flags

[Paragraph]
Designers, team leads, CS, management, project owners and admins.
```

### 15. `projects.notes` — Notes and chat

_Status: written (earlier chat). Needs splitting: keep Site visits here, move Chat into 35._

```
Section: Projects

[Paragraph]
Two different things sit here. Chat is the conversation about the project. Notes is the site visit log.

[Heading] Chat

[List]

Type @ to mention someone. They get notified
Reply to a message to keep a thread together
React with an emoji
Pin a message so it stays at the top
Attach files
Copy or delete your own messages

[Paragraph]
Messages are grouped by day. You can also reach project chat from the Chat tray on the right edge, without opening the project.

[Callout]
A project row can show two dots. One is a new update, cleared by opening the project. The other is a new chat message, cleared only by opening Chat. A busy chat will never hide a real change to the work.

[Heading] Site visits

[List]

Add Site Visit, then set Location, Start, End and the Designer
Location Link is optional. Paste a maps link so nobody has to search for the place
Notes are optional

[Callout]
One person cannot be in two places at once. If the times overlap a visit that person already has, the app refuses it and tells you which one it clashes with.

[Heading] Who can post

[Paragraph]
Anyone actually on the project: the CS Lead, Secondary CS, the Project Owner, assigned designers, management and admins.
```

### 35. `chat.projects` — Project chat

_Status: not written yet — take the Chat half of 15_
