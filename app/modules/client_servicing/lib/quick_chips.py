"""
The Table's quick filter chips and which rows each one matches. Decided on the
server with the Dashboard's own rules, so a chip counts what the Dashboard counts.
"""
from app.modules.client_servicing.lib.data_gaps import MISSING_DATA_CHIP, missing_fields

MINE_CHIP = 'mine'
AT_RISK_CHIP = 'at_risk'
INSTALLS_MONTH_CHIP = 'installs_month'

# (id, label) in display order. client_servicing.js declares the same ids in
# TEMPLATE_CONTRACT; a test keeps the two lists equal.
CHIPS = [
    (MINE_CHIP, 'My jobs'),
    (MISSING_DATA_CHIP, 'Missing data'),
    (AT_RISK_CHIP, 'At risk'),
    (INSTALLS_MONTH_CHIP, 'Installs this month'),
]


def row_chips(project, risk, user_id, today):
    """Chip ids this project matches. `risk` is its effective risk label;
    "mine" means the user is its CS lead or project owner."""
    chips = []
    if user_id is not None and user_id in (project.cs_lead_id, project.project_owner_id):
        chips.append(MINE_CHIP)
    if missing_fields(project):
        chips.append(MISSING_DATA_CHIP)
    if risk == 'At Risk':
        chips.append(AT_RISK_CHIP)
    d = project.installation_date
    if d and d.year == today.year and d.month == today.month:
        chips.append(INSTALLS_MONTH_CHIP)
    return chips
