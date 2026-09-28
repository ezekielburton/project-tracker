# HSE & Compliance module

The site HSE officer's workspace. It replaces his spreadsheet of 21 tabs with
one place to log safety work, plan his week, and report on it. Off-roadmap;
ships as a patch.

## What's in it

- **Overview** — what needs him now, what's waiting on others, what's expiring,
  and this week at a glance.
- **Daily log** — what he finds on his daily rounds, open until resolved.
- **Calendar** — his week. Planned checks come from recurring schedules; he
  logs work straight from a day. The **Schedule** tab sets those schedules up.
- **Registers** — 21 more, grouped on the side rail:
  - Incidents: incident & near miss, first aid, PPE non-conformity, lost time injury
  - Inspections: general, vehicle, forklift
  - Compliance: compliance & renewal
  - Fleet: vehicle service, reg & insurance, mileage
  - Machines: maintenance, preventive maintenance, machine cost
  - Stores: PPE register, tools inventory, material request, materials in stock
  - Training: induction, toolbox talk, training expenses
- **Lists & people** — his own locations, departments, people, assets and
  dropdown lists. He manages these himself, not an admin.
- **My performance** — the numbers he takes to a review, with a printable PDF.

## How it works

- Every register is declared once in `lib/registers.py`. Forms, tables and
  filters are built from that, so a new register is one entry, not a feature.
- All entries live in one table (`HseEntry`); register-specific fields sit in
  a JSON column.
- Anything calculated (days open, days to expiry, expiry status, time to close)
  is worked out when shown, never saved.
- Spend is the sum of every declared `money` field, by entry date, worked out
  when shown; the Overview and register strips share `query.spend_entries`.
- A time field is `HH:MM` (24-hour), kept in the JSON column.
- A machine's serial number lives on the asset (`serial_no`, set in Lists &
  people) and shows read-only under the picker in the machine registers.
- Nothing is deleted. Retired list items, people and assets are deactivated.
- Time an action spends waiting on someone else doesn't count against him.
- Attachments are stored on the NAS under `/HSE/<register>/<ref>`.
- Other modules read HSE numbers only through `services/feed.py`.

## Who sees what

- **HSE officer** — reads and edits everything in the module, and sees only this
  module in his sidebar.
- **Management** — reads everything, edits nothing.
- **Admin** — reads and edits everything.
- **My performance** — everyone sees their own; management and admin see anyone's.

## Dev data

`python dev_seed_hse_demo.py` adds demo entries; `--wipe` removes only those.
Dev only — never run on the server.
