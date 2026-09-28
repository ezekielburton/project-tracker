"""
Service-due and low-stock flags: vehicles near their next service by km,
machines near their next preventive maintenance by date, and materials at
or below their reorder level. All computed at read time; nothing is stored.
"""

from datetime import date, timedelta

from app.modules.hse.lib import stock
from app.modules.hse.lib.computed import latest_by_asset, next_due
from app.modules.hse.lib.overview import entry_title
from app.modules.hse.lib.query import eager, open_counts_by_register
from app.modules.hse.lib.registers import BY_KEY
from app.modules.hse.lib.spend import amount_text
from app.modules.hse.models import HseEntry


# How close counts as "due soon".
SERVICE_SOON_KM = 1000
PM_SOON_DAYS = 7

SERVICE_REGISTER = 'vehicle_service'
MILEAGE_REGISTER = 'vehicle_mileage'
PM_REGISTER = 'machine_preventive'
STOCK_REGISTER = 'materials_in_stock'

# Only a completed service sets the next one.
SERVICE_DONE = 'Completed'

# The filter chip each flagged register gets: (URL value, label).
FLAG_CHIPS = {
    SERVICE_REGISTER: ('due', 'Due'),
    PM_REGISTER: ('due', 'Due'),
    STOCK_REGISTER: ('low', 'Low stock'),
}

# Panel order: overdue first, then low stock, then due soon.
_STATE_ORDER = {'overdue': 0, 'low': 1, 'soon': 2}


def as_number(value):
    """A stored reading as a number, or None."""
    if value is None or isinstance(value, bool) or value == '':
        return None
    try:
        number = float(str(value).replace(',', ''))
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def km_text(value):
    """'12,500 km'."""
    return f'{amount_text(value)} km'


def current_services(services):
    """asset_id -> the latest completed service for it."""
    return latest_by_asset(e for e in services if e.status == SERVICE_DONE)


def next_service_km(entry):
    """Mileage at service plus the interval, or None when either is missing."""
    mileage_field, interval_field = BY_KEY[SERVICE_REGISTER].km_due
    data = entry.data or {}
    mileage, interval = as_number(data.get(mileage_field)), as_number(data.get(interval_field))
    if mileage is None or not interval:
        return None
    return mileage + interval


def odometers(mileage_entries):
    """asset_id -> highest odometer reading logged. Odometers only go up,
    so the highest is the latest."""
    out = {}
    for entry in mileage_entries:
        reading = as_number((entry.data or {}).get('odometer'))
        if entry.asset_id is None or reading is None:
            continue
        out[entry.asset_id] = max(out.get(entry.asset_id, reading), reading)
    return out


def service_state(entry, odometer):
    """(state, km left) for a vehicle's current service: state is
    'overdue', 'soon' or None. The service's own mileage stands in when no
    later odometer reading exists."""
    due_km = next_service_km(entry)
    if due_km is None:
        return None, None
    mileage = as_number((entry.data or {}).get(BY_KEY[SERVICE_REGISTER].km_due[0])) or 0
    current = max(odometer or 0, mileage)
    left = due_km - current
    if left <= 0:
        return 'overdue', left
    if left <= SERVICE_SOON_KM:
        return 'soon', left
    return None, left


def pm_state(entry, today=None, reg=None):
    """(state, due date) for a machine's current preventive maintenance.
    `reg` defaults to Preventive maintenance."""
    today = today or date.today()
    due = next_due(entry, reg or BY_KEY[PM_REGISTER])
    if due is None:
        return None, None
    if due < today:
        return 'overdue', due
    if due <= today + timedelta(days=PM_SOON_DAYS):
        return 'soon', due
    return None, due


def _row(entry, state, detail):
    return {
        'entry': entry,
        'ref': entry.ref,
        'register': entry.register,
        'register_label': BY_KEY[entry.register].label,
        'title': entry_title(entry),
        'state': state,
        'detail': detail,
    }


def _days(n):
    return f'{n}d'


def flags(entries, today=None):
    """Every flagged item across the three registers, in panel order.
    `entries` must hold all rows of those registers plus Mileage."""
    today = today or date.today()
    by_register = {}
    for entry in entries:
        by_register.setdefault(entry.register, []).append(entry)

    out = []
    readings = odometers(by_register.get(MILEAGE_REGISTER, ()))
    for asset_id, entry in current_services(by_register.get(SERVICE_REGISTER, ())).items():
        state, left = service_state(entry, readings.get(asset_id))
        if state == 'overdue':
            out.append(_row(entry, state, f'{km_text(-left)} over' if left else 'due now'))
        elif state == 'soon':
            out.append(_row(entry, state, f'{km_text(left)} left'))

    pm = by_register.get(PM_REGISTER, ())
    for entry in latest_by_asset(pm).values():
        state, due = pm_state(entry, today)
        if state == 'overdue':
            out.append(_row(entry, state, f'{_days((today - due).days)} overdue'))
        elif state == 'soon':
            days = (due - today).days
            out.append(_row(entry, state, 'due today' if not days else f'{_days(days)} left'))

    for entry in by_register.get(STOCK_REGISTER, ()):
        if stock.is_low_stock(entry):
            out.append(_row(entry, 'low', f'{stock.balance_text(entry)} left'))

    out.sort(key=lambda r: (_STATE_ORDER[r['state']], r['register_label'], r['title']))
    return out


def load_flags(today=None):
    """flags() over every row of the flagged registers. Small sets: one row
    per vehicle service, machine PM, mileage log and stock line."""
    registers = (SERVICE_REGISTER, MILEAGE_REGISTER, PM_REGISTER, STOCK_REGISTER)
    entries = eager(HseEntry.query.filter(HseEntry.register.in_(registers))).all()
    return flags(entries, today)


def service_context():
    """(ids of each vehicle's latest completed service, odometer per
    vehicle), for the Vehicle service table's Next service column."""
    entries = HseEntry.query.filter(
        HseEntry.register.in_((SERVICE_REGISTER, MILEAGE_REGISTER))).all()
    services = [e for e in entries if e.register == SERVICE_REGISTER]
    mileage = [e for e in entries if e.register == MILEAGE_REGISTER]
    return {e.id for e in current_services(services).values()}, odometers(mileage)


def rail_counts(today=None, rows=None):
    """Rail badges: open items plus flagged items per register. Pass `rows`
    when the page has already loaded the flags."""
    counts = open_counts_by_register(today)
    for key, n in flag_counts(load_flags(today) if rows is None else rows).items():
        counts[key] = counts.get(key, 0) + n
    return counts


def flag_counts(rows):
    """register key -> number of flagged items."""
    counts = {}
    for r in rows:
        counts[r['register']] = counts.get(r['register'], 0) + 1
    return counts


def flagged_ids(rows, register_key):
    """Ids of the flagged entries in one register."""
    return {r['entry'].id for r in rows if r['register'] == register_key}


def panel(rows, limit):
    """The Overview panel: the first `limit` rows and how many more."""
    return {'rows': rows[:limit], 'total': len(rows), 'more': max(0, len(rows) - limit)}
