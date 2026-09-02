# Digital Innovation — Cost ledger Excel export (Phase 3). One function,
# one job: turn a project's cost_summary() (lib/costs.py) into an .xlsx
# workbook. Kept separate from routes/costs.py the same way board_data.py
# is kept separate from routes/board.py — the route layer just streams
# whatever this returns.

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

from app.modules.digital_innovation.lib.costs import DI_COST_TYPE_LABELS

_HEADER_FILL = PatternFill(start_color='4A4A4A', end_color='4A4A4A', fill_type='solid')


def build_cost_ledger_workbook(di_project, summary):
    """Builds the workbook in memory and returns a BytesIO positioned at
    the start, ready to hand straight to Flask's send_file. `summary` is
    whatever lib.costs.cost_summary(di_project) returned — the route
    already has it (it just rendered the modal from it), so this doesn't
    re-query."""
    wb = Workbook()
    ws = wb.active
    ws.title = 'Cost Ledger'

    bold = Font(bold=True)
    header_font = Font(bold=True, color='FFFFFF')

    ws['A1'] = di_project.name
    ws['A1'].font = Font(bold=True, size=14)
    ws['A2'] = f'Cost ledger — exported {datetime.utcnow().strftime("%d %b %Y")}'
    ws['A2'].font = Font(italic=True, color='666666')

    headers = ['Date', 'Type', 'Feature', 'Description', 'Hours', 'Amount']
    header_row = 4
    for col, label in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col, value=label)
        cell.font = header_font
        cell.alignment = Alignment(horizontal='left')
        cell.fill = _HEADER_FILL

    row = header_row + 1
    # Ledger's own display order is newest-first (better for the on-screen
    # table); the export reverses to oldest-first, which reads more
    # naturally as a spreadsheet log.
    for entry in reversed(summary['entries']):
        ws.cell(row=row, column=1, value=entry.date)
        ws.cell(row=row, column=1).number_format = 'yyyy-mm-dd'
        ws.cell(row=row, column=2, value=DI_COST_TYPE_LABELS.get(entry.type, entry.type))
        ws.cell(row=row, column=3, value=entry.feature.name if entry.feature else '')
        ws.cell(row=row, column=4, value=entry.description or '')
        ws.cell(row=row, column=5, value=entry.hours if entry.hours else None)
        ws.cell(row=row, column=6, value=entry.amount)
        row += 1

    totals_row = row + 1
    ws.cell(row=totals_row, column=5, value='Total cost').font = bold
    ws.cell(row=totals_row, column=6, value=summary['total_cost']).font = bold

    if summary['client_charge'] is not None:
        ws.cell(row=totals_row + 1, column=5, value='Client charge').font = bold
        ws.cell(row=totals_row + 1, column=6, value=summary['client_charge']).font = bold
        ws.cell(row=totals_row + 2, column=5, value='Projected profit').font = bold
        ws.cell(row=totals_row + 2, column=6, value=summary['projected_profit']).font = bold

    widths = [12, 12, 22, 34, 9, 12]
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
