# HSE & Compliance

### 25. `hse.overview` — HSE overview

_Status: not written yet_

### 26. `hse.registers` — Registers

_Status: written 2026-09-30_

```
Section: HSE & Compliance

[Paragraph]
Every register works the same way: filters on top, the table below, and the entry form when you click a row or press New entry.

[Heading] The table

[List]

Status chips - All, then each status with its count. Fleet, machine and stock registers also have Due and Low stock
Search looks across every field, names included
Long text wraps to two lines. Hover a row to read it in full
Click a row to open it

[Heading] The entry form

[List]

Fields with a star are required
The ref (INC-0001) is given when you save
Days open and days to expiry are worked out, never typed
Attach photos, PDFs or documents once the entry is saved

[Heading] Who is on an entry

[List]

Reported by - who reported it. Starts on you
Reported to - who it was reported to
Done by - who did the work, named for the register: Treated by, Inspector, Technician, Trainer, Conducted by
Employee, Driver or Operator - who it is about
Waiting on - someone else who has the next step. That time is not counted against you

[Paragraph]
People with HSE in their name or role are listed first in every person picker.

[Callout]
Nothing is deleted. A value retired on Lists & people stays on the entries that already used it, shown struck through.
```

### 27. `hse.schedule` — Scheduling inspections

_Status: not written yet_

### 28. `hse.calendar` — The HSE calendar

_Status: not written yet_

### 29. `hse.performance` — HSE performance

_Status: written 2026-09-30_

```
Section: HSE & Compliance

[Paragraph]
My performance measures what you control over a month or a year, ready for a review. It is not a score for how safe the site is.

[Heading] Choosing a period

[List]

Month or Year. Year is the twelve months up to the month shown
The arrows step back and forward. Back to now returns to the current month
Every figure compares with the period before

[Heading] The tiles

[List]

Actions closed on time - within the SLA: Critical 4, High 7, Medium 15, Low 30 days
Average time to close - time waiting on others is shown separately
Inspection coverage - planned inspections done, and how many were carried out in total
Training delivered - sessions and attendees. Only completed talks count
Spend - AED across every cost register. It shows the change, not better or worse

[Heading] The panels

[List]

Spend - totals to date, then the period by area
Reporting culture - near misses per incident, plus how many were logged and are still open
Compliance health - items valid today, renewals done on time, and any that lapsed, by name
Open actions, by age

[Heading] Sharing it

[List]

Export for review - the four-page PDF
Email - the headline numbers and a link
CSV - the figures as a spreadsheet

[Callout]
More near misses is the good result. It means hazards are being reported before somebody gets hurt. A falling number usually means under-reporting, not a safer site.
```

### 30. `hse.lists` — Lists & people

_Status: written 2026-09-30_

```
Section: HSE & Compliance

[Paragraph]
Lists & people holds everything the HSE dropdowns are filled from. You manage it yourself, no admin needed.

[Heading] Finding a list

[List]

Basics - Locations, Departments, People
Assets - Vehicles, Machines, Forklifts, Areas
Choice lists - every other dropdown, A to Z
Find a list filters the index as you type. The number beside a list is how many values are in use

[Heading] Adding and editing

[List]

Type in the first row of the table and press Add or Enter
Click a name, plate or serial to change it. Enter saves, Escape undoes
Deactivate retires a value. It leaves the dropdowns but stays on every entry that already used it
Show retired lists retired values, each with Reactivate

[Heading] People

[Paragraph]
Add person, or clicking a row, opens a panel with name, role, organisation, email and phone. Two switches matter:

[List]

External - not company staff
Actions can wait on them - puts them in Waiting on. Time an action spends with them is not counted against your time to close

[Paragraph]
Anyone with HSE in their name or role is listed first in every person picker.

[Callout]
People and assets cannot be added from inside an entry form. Fill them in here before logging the first entry. An empty People or Assets list shows Empty in the index.
```
